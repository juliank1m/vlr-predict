"""Walk-forward model training pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SyncSessionLocal
from app.ml.evaluate import calibration_curve_data, summarize_binary_predictions
from app.ml.feature_importance import rank_feature_importance
from app.services.features import DEFAULT_MEDIANS, FEATURE_NAMES, compute_features
from app.services.predictor import resolve_artifact_path

_TRAINING_ROWS_SQL = text(
    """
    SELECT
        m.id AS map_id,
        mt.id AS match_id,
        mt.date AS match_date,
        mt.team1_id,
        mt.team2_id,
        m.map_name,
        m.map_number,
        m.winner_id
    FROM maps m
    JOIN matches mt ON mt.id = m.match_id
    WHERE mt.date IS NOT NULL
      AND mt.team1_id IS NOT NULL
      AND mt.team2_id IS NOT NULL
      AND m.winner_id IN (mt.team1_id, mt.team2_id)
    ORDER BY mt.date, m.map_number, m.id
    """
)


@dataclass(frozen=True)
class EstimatorSpec:
    estimator: Any
    model_type: str
    warning: str | None = None


TUNING_GRID = [
    {"n_estimators": 300, "max_depth": 5, "learning_rate": 0.05, "subsample": 0.9, "colsample_bytree": 0.8, "reg_lambda": 1.0},
    {"n_estimators": 500, "max_depth": 4, "learning_rate": 0.03, "subsample": 0.8, "colsample_bytree": 0.7, "reg_lambda": 2.0},
    {"n_estimators": 400, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.85, "colsample_bytree": 0.85, "reg_lambda": 0.5},
    {"n_estimators": 300, "max_depth": 3, "learning_rate": 0.1, "subsample": 0.9, "colsample_bytree": 0.9, "reg_lambda": 1.0},
    {"n_estimators": 600, "max_depth": 5, "learning_rate": 0.02, "subsample": 0.85, "colsample_bytree": 0.75, "reg_lambda": 1.5},
    {"n_estimators": 400, "max_depth": 4, "learning_rate": 0.08, "subsample": 0.9, "colsample_bytree": 0.8, "reg_lambda": 0.8},
    {"n_estimators": 500, "max_depth": 3, "learning_rate": 0.05, "subsample": 0.85, "colsample_bytree": 0.9, "reg_lambda": 1.5},
    {"n_estimators": 200, "max_depth": 6, "learning_rate": 0.1, "subsample": 0.8, "colsample_bytree": 0.7, "reg_lambda": 2.0},
]


def build_estimator(preferred_model: str = "auto") -> EstimatorSpec:
    """Create the primary estimator, falling back when XGBoost is unavailable."""
    if preferred_model in {"auto", "xgboost"}:
        try:
            from xgboost import XGBClassifier

            return EstimatorSpec(
                estimator=XGBClassifier(
                    n_estimators=300,
                    max_depth=5,
                    learning_rate=0.05,
                    subsample=0.9,
                    colsample_bytree=0.8,
                    reg_lambda=1.0,
                    random_state=42,
                    eval_metric="logloss",
                    tree_method="hist",
                ),
                model_type="xgboost",
            )
        except Exception as exc:  # pragma: no cover - environment-specific
            if preferred_model == "xgboost":
                raise
            return EstimatorSpec(
                estimator=HistGradientBoostingClassifier(
                    max_depth=5,
                    learning_rate=0.05,
                    max_iter=300,
                    l2_regularization=0.1,
                    random_state=42,
                ),
                model_type="hist_gradient_boosting",
                warning=f"XGBoost unavailable; used HistGradientBoostingClassifier instead: {exc}",
            )

    if preferred_model == "hist_gradient_boosting":
        return EstimatorSpec(
            estimator=HistGradientBoostingClassifier(
                max_depth=5,
                learning_rate=0.05,
                max_iter=300,
                l2_regularization=0.1,
                random_state=42,
            ),
            model_type="hist_gradient_boosting",
        )

    raise ValueError(f"Unsupported model type: {preferred_model}")


def elo_probability_from_diff(elo_diff: pd.Series | np.ndarray) -> np.ndarray:
    """Convert Elo differences to win probabilities."""
    diff = np.asarray(elo_diff, dtype=float)
    return 1.0 / (1.0 + np.power(10.0, -diff / 400.0))


def default_feature_imputation() -> dict[str, float]:
    """Fallback imputation for any feature column with no observed history."""
    defaults: dict[str, float] = {}
    for name in FEATURE_NAMES:
        if name == "team1_elo" or name == "team2_elo":
            defaults[name] = 1500.0
        elif name == "elo_diff":
            defaults[name] = 0.0
        elif "_avg_rating_" in name:
            defaults[name] = DEFAULT_MEDIANS["avg_rating"]
        elif "_avg_acs_" in name:
            defaults[name] = DEFAULT_MEDIANS["avg_acs"]
        elif "_avg_kast_" in name:
            defaults[name] = DEFAULT_MEDIANS["avg_kast"]
        elif "_avg_adr_" in name:
            defaults[name] = DEFAULT_MEDIANS["avg_adr"]
        elif "_fk_rate_" in name:
            defaults[name] = DEFAULT_MEDIANS["fk_rate"]
        elif "_fd_rate_" in name:
            defaults[name] = DEFAULT_MEDIANS["fd_rate"]
        elif "_win_rate_" in name or name.endswith("_map_win_rate") or name == "h2h_team1_win_rate":
            defaults[name] = DEFAULT_MEDIANS["win_rate"]
        elif "map_games_played" in name or name == "h2h_maps_played":
            defaults[name] = 0.0
        elif name.endswith("_days_since_last"):
            defaults[name] = 30.0
        elif name.endswith("_streak") or name.endswith("_recent_momentum") or name.endswith("_diff"):
            defaults[name] = 0.0
        elif name.endswith("_roster_overlap"):
            defaults[name] = 0.5
        elif name.startswith("is_team") and "_pick" in name:
            defaults[name] = 0.0
        elif name == "is_decider":
            defaults[name] = 1.0
        elif name.endswith("_pick_win_rate"):
            defaults[name] = 0.5
        elif name.endswith("_map_elo"):
            defaults[name] = 1500.0
        elif name == "map_elo_diff":
            defaults[name] = 0.0
        elif name.endswith("_pistol_wr"):
            defaults[name] = 0.5
        elif name.endswith("_attack_wr"):
            defaults[name] = 0.5
        elif name.endswith("_defense_wr"):
            defaults[name] = 0.5
        elif name.endswith("_comeback_rate"):
            defaults[name] = 0.3
        elif name in ("pistol_wr_diff", "attack_wr_diff", "defense_wr_diff"):
            defaults[name] = 0.0
        else:
            defaults[name] = 0.0
    return defaults


def compute_imputation_values(frame: pd.DataFrame) -> dict[str, float]:
    """Median imputation with neutral fallbacks for fully-null columns."""
    defaults = default_feature_imputation()
    medians = frame.median(numeric_only=True).to_dict()
    values = defaults.copy()
    for key, value in medians.items():
        if pd.notna(value):
            values[str(key)] = float(value)
    return values


def apply_imputation(frame: pd.DataFrame, imputation_values: dict[str, float]) -> pd.DataFrame:
    """Fill missing values and ensure a stable float matrix."""
    return frame.fillna(value=imputation_values).astype(float)


def load_training_rows(session: Session, limit: int | None = None) -> list[dict[str, Any]]:
    """Load chronologically ordered resolved maps for training."""
    rows = session.execute(_TRAINING_ROWS_SQL).mappings().all()
    if limit is not None:
        rows = rows[:limit]
    return [dict(row) for row in rows]


def build_training_dataset(session: Session, *, limit: int | None = None, cancel_check: callable = None) -> pd.DataFrame:
    """Compute feature rows for every resolved historical map."""
    records: list[dict[str, Any]] = []
    rows = load_training_rows(session, limit=limit)
    total = len(rows)
    logger.info("Computing features for %d maps...", total)

    for i, row in enumerate(rows):
        if (i + 1) % 500 == 0:
            logger.info("  %d/%d maps featurized...", i + 1, total)
            if cancel_check:
                cancel_check()
        features = compute_features(
            session,
            team1_id=int(row["team1_id"]),
            team2_id=int(row["team2_id"]),
            map_name=row["map_name"],
            match_date=row["match_date"],
            map_id=int(row["map_id"]),
        )
        record = {
            "map_id": int(row["map_id"]),
            "match_id": int(row["match_id"]),
            "match_date": row["match_date"],
            "month": pd.Timestamp(row["match_date"]).to_period("M").to_timestamp(),
            "team1_id": int(row["team1_id"]),
            "team2_id": int(row["team2_id"]),
            "map_name": row["map_name"],
            "target": 1 if int(row["winner_id"]) == int(row["team1_id"]) else 0,
        }
        record.update(features)
        records.append(record)

    if not records:
        raise ValueError("No resolved maps available for training.")
    return pd.DataFrame.from_records(records)


def walk_forward_months(dataset: pd.DataFrame, min_train_months: int) -> tuple[list[pd.Timestamp], pd.Timestamp]:
    """Return validation months and the final held-out test month."""
    months = sorted(pd.Timestamp(month) for month in dataset["month"].drop_duplicates())
    if len(months) <= min_train_months:
        raise ValueError("Not enough months of data for walk-forward validation.")
    return months[:-1], months[-1]


def _evaluate_split(
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    *,
    preferred_model: str,
) -> tuple[dict[str, Any], Any, dict[str, float], pd.DataFrame]:
    X_train = train_df[FEATURE_NAMES]
    y_train = train_df["target"]
    X_eval = eval_df[FEATURE_NAMES]
    y_eval = eval_df["target"]

    imputation_values = compute_imputation_values(X_train)
    X_train_filled = apply_imputation(X_train, imputation_values)
    X_eval_filled = apply_imputation(X_eval, imputation_values)

    spec = build_estimator(preferred_model=preferred_model)
    model = spec.estimator
    model.fit(X_train_filled, y_train)
    probs = model.predict_proba(X_eval_filled)[:, 1]

    fold_metrics = {
        "coin_flip": summarize_binary_predictions(y_eval, np.full(len(y_eval), 0.5)),
        "elo_only": summarize_binary_predictions(y_eval, elo_probability_from_diff(X_eval_filled["elo_diff"])),
        "full_model": summarize_binary_predictions(y_eval, probs),
    }
    if spec.warning is not None:
        fold_metrics["warning"] = spec.warning

    return fold_metrics, model, imputation_values, X_eval_filled


def _mean_metric_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for model_name in ("coin_flip", "elo_only", "full_model"):
        summary[model_name] = {
            metric: float(np.mean([row[model_name][metric] for row in rows]))
            for metric in ("log_loss", "brier_score", "accuracy")
        }
    return summary


def train_and_save(
    *,
    limit: int | None = None,
    min_train_months: int = 6,
    preferred_model: str = "auto",
    cancel_check: callable = None,
) -> dict[str, Any]:
    """Train the model, evaluate it, and persist artifacts."""
    logger.info("Building training dataset...")
    with SyncSessionLocal() as session:
        dataset = build_training_dataset(session, limit=limit, cancel_check=cancel_check)
    logger.info("Dataset: %d rows", len(dataset))

    cv_months, test_month = walk_forward_months(dataset, min_train_months)
    logger.info("Walk-forward CV: %d folds, test month: %s", len(cv_months) - min_train_months, test_month.date())
    fold_results: list[dict[str, Any]] = []

    for idx in range(min_train_months, len(cv_months)):
        validate_month = cv_months[idx]
        train_mask = dataset["month"] < validate_month
        eval_mask = dataset["month"] == validate_month
        train_df = dataset.loc[train_mask]
        eval_df = dataset.loc[eval_mask]
        if train_df.empty or eval_df.empty:
            continue

        logger.info("  Fold %d/%d: train=%d, validate=%d (%s)",
                     idx - min_train_months + 1, len(cv_months) - min_train_months,
                     len(train_df), len(eval_df), validate_month.date())
        metrics, _, _, _ = _evaluate_split(
            train_df,
            eval_df,
            preferred_model=preferred_model,
        )
        fold_results.append(
            {
                "train_end_month": train_df["month"].max().date().isoformat(),
                "validate_month": validate_month.date().isoformat(),
                "train_size": int(len(train_df)),
                "validate_size": int(len(eval_df)),
                "coin_flip": metrics["coin_flip"],
                "elo_only": metrics["elo_only"],
                "full_model": metrics["full_model"],
                "warning": metrics.get("warning"),
            }
        )

    logger.info("Final test split on %s...", test_month.date())
    train_df = dataset.loc[dataset["month"] < test_month].copy()
    test_df = dataset.loc[dataset["month"] == test_month].copy()
    if train_df.empty or test_df.empty:
        raise ValueError("Unable to create final train/test split.")
    logger.info("  Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    test_metrics, fitted_model, test_imputation, X_test_filled = _evaluate_split(
        train_df,
        test_df,
        preferred_model=preferred_model,
    )
    test_probs = fitted_model.predict_proba(X_test_filled)[:, 1]
    feature_importances = rank_feature_importance(
        fitted_model,
        FEATURE_NAMES,
        X_reference=X_test_filled,
        y_reference=test_df["target"],
    )

    logger.info("Training final model on all %d rows...", len(dataset))
    full_imputation = compute_imputation_values(dataset[FEATURE_NAMES])
    X_full = apply_imputation(dataset[FEATURE_NAMES], full_imputation)
    final_spec = build_estimator(preferred_model=preferred_model)
    final_model = final_spec.estimator
    final_model.fit(X_full, dataset["target"])
    logger.info("Model trained (%s). Saving artifacts...", final_spec.model_type)

    settings = get_settings()
    model_path = resolve_artifact_path(settings.model_path)
    feature_config_path = resolve_artifact_path(settings.feature_config_path)
    metadata_path = resolve_artifact_path(settings.training_metadata_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    feature_config_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    trained_at = datetime.now(UTC).isoformat()
    model_version = (
        "xgb_v1"
        if final_spec.model_type == "xgboost"
        else "hgb_v1"
    )

    feature_config = {
        "created_at": trained_at,
        "feature_names": FEATURE_NAMES,
        "imputation_values": full_imputation,
    }
    metadata = {
        "trained_at": trained_at,
        "model_version": model_version,
        "model_type": final_spec.model_type,
        "warning": final_spec.warning,
        "feature_count": len(FEATURE_NAMES),
        "row_count": int(len(dataset)),
        "date_range": {
            "start": pd.Timestamp(dataset["match_date"].min()).isoformat(),
            "end": pd.Timestamp(dataset["match_date"].max()).isoformat(),
        },
        "temporal_cv": {
            "min_train_months": min_train_months,
            "folds": fold_results,
            "summary": _mean_metric_rows(fold_results) if fold_results else {},
        },
        "test": {
            "month": test_month.date().isoformat(),
            "train_size": int(len(train_df)),
            "test_size": int(len(test_df)),
            "coin_flip": test_metrics["coin_flip"],
            "elo_only": test_metrics["elo_only"],
            "full_model": test_metrics["full_model"],
            "calibration": calibration_curve_data(test_df["target"], test_probs),
        },
        "feature_importances": feature_importances,
        "artifact_training": {
            "trained_on_full_history": True,
            "full_training_rows": int(len(dataset)),
        },
    }

    if final_spec.warning is not None:
        metadata["warning"] = final_spec.warning

    joblib.dump(final_model, model_path)
    feature_config_path.write_text(json.dumps(feature_config, indent=2), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    test_acc = test_metrics["full_model"].get("accuracy", 0)
    logger.info("Artifacts saved. Version=%s, rows=%d, test_accuracy=%.3f", model_version, len(dataset), test_acc)
    return metadata


def tune_and_save(
    *,
    min_train_months: int = 6,
    cancel_check: callable = None,
) -> dict[str, Any]:
    """Try multiple hyperparameter configs, pick the best by CV log-loss, then train final model."""
    logger.info("Building training dataset for tuning...")
    with SyncSessionLocal() as session:
        dataset = build_training_dataset(session, cancel_check=cancel_check)
    logger.info("Dataset: %d rows, testing %d configs", len(dataset), len(TUNING_GRID))

    cv_months, test_month = walk_forward_months(dataset, min_train_months)

    # Use last 3 CV months as validation for tuning
    tune_months = cv_months[-3:] if len(cv_months) >= 3 else cv_months
    best_loss = float("inf")
    best_params = TUNING_GRID[0]
    results = []

    for ci, params in enumerate(TUNING_GRID):
        if cancel_check:
            cancel_check()
        logger.info("Config %d/%d: %s", ci + 1, len(TUNING_GRID), params)

        fold_losses = []
        for month in tune_months:
            train_mask = dataset["month"] < month
            eval_mask = dataset["month"] == month
            train_df = dataset.loc[train_mask]
            eval_df = dataset.loc[eval_mask]
            if train_df.empty or eval_df.empty:
                continue

            X_train = train_df[FEATURE_NAMES]
            y_train = train_df["target"]
            X_eval = eval_df[FEATURE_NAMES]
            y_eval = eval_df["target"]

            imputation_values = compute_imputation_values(X_train)
            X_train_filled = apply_imputation(X_train, imputation_values)
            X_eval_filled = apply_imputation(X_eval, imputation_values)

            try:
                from xgboost import XGBClassifier
                model = XGBClassifier(
                    **params,
                    random_state=42,
                    eval_metric="logloss",
                    tree_method="hist",
                )
                model.fit(X_train_filled, y_train)
                probs = model.predict_proba(X_eval_filled)[:, 1]
                metrics = summarize_binary_predictions(y_eval, probs)
                fold_losses.append(metrics["log_loss"])
            except Exception as e:
                logger.warning("Config %d failed on fold: %s", ci + 1, e)
                continue

        if fold_losses:
            avg_loss = float(np.mean(fold_losses))
            avg_acc = None
            # Quick accuracy check on last fold
            results.append({"config": params, "avg_log_loss": avg_loss, "folds": len(fold_losses)})
            logger.info("  Avg log-loss: %.4f (%d folds)", avg_loss, len(fold_losses))
            if avg_loss < best_loss:
                best_loss = avg_loss
                best_params = params

    logger.info("Best config (log-loss=%.4f): %s", best_loss, best_params)
    logger.info("Training candidate model with best params...")

    from xgboost import XGBClassifier

    train_df = dataset.loc[dataset["month"] < test_month].copy()
    test_df = dataset.loc[dataset["month"] == test_month].copy()

    X_train = train_df[FEATURE_NAMES]
    y_train = train_df["target"]
    X_test = test_df[FEATURE_NAMES]
    y_test = test_df["target"]

    imputation_values = compute_imputation_values(X_train)
    X_train_filled = apply_imputation(X_train, imputation_values)
    X_test_filled = apply_imputation(X_test, imputation_values)

    best_model = XGBClassifier(
        **best_params,
        random_state=42,
        eval_metric="logloss",
        tree_method="hist",
    )
    best_model.fit(X_train_filled, y_train)
    test_probs = best_model.predict_proba(X_test_filled)[:, 1]
    test_metrics = summarize_binary_predictions(y_test, test_probs)
    tuned_acc = test_metrics["accuracy"]
    logger.info("Tuned test accuracy: %.3f (log-loss: %.4f)", tuned_acc, test_metrics["log_loss"])

    # Train on full dataset and save as candidate (not active)
    full_imputation = compute_imputation_values(dataset[FEATURE_NAMES])
    X_full = apply_imputation(dataset[FEATURE_NAMES], full_imputation)
    final_model = XGBClassifier(
        **best_params,
        random_state=42,
        eval_metric="logloss",
        tree_method="hist",
    )
    final_model.fit(X_full, dataset["target"])

    settings = get_settings()
    artifacts_dir = resolve_artifact_path(settings.model_path).parent

    # Save candidate model separately — does NOT overwrite active model
    candidate_model_path = artifacts_dir / "model_candidate.joblib"
    candidate_config_path = artifacts_dir / "feature_config_candidate.json"
    tuning_path = artifacts_dir / "tuning_result.json"

    trained_at = datetime.now(UTC).isoformat()
    candidate_config = {
        "created_at": trained_at,
        "feature_names": FEATURE_NAMES,
        "imputation_values": full_imputation,
    }

    # Read current model accuracy for comparison
    current_metadata_path = resolve_artifact_path(settings.training_metadata_path)
    current_acc = None
    if current_metadata_path.exists():
        try:
            current_meta = json.loads(current_metadata_path.read_text())
            current_acc = current_meta.get("test", {}).get("full_model", {}).get("accuracy")
        except Exception:
            pass

    joblib.dump(final_model, candidate_model_path)
    candidate_config_path.write_text(json.dumps(candidate_config, indent=2), encoding="utf-8")

    tuning_result = {
        "best_params": best_params,
        "best_cv_log_loss": best_loss,
        "tuned_test_accuracy": tuned_acc,
        "current_test_accuracy": current_acc,
        "all_results": results,
        "tuned_at": trained_at,
        "status": "pending",  # "pending" = waiting for user to accept/reject
    }
    tuning_path.write_text(json.dumps(tuning_result, indent=2), encoding="utf-8")

    if current_acc is not None:
        logger.info("Current model: %.1f%% | Tuned model: %.1f%% — use Accept/Reject in admin panel",
                     current_acc * 100, tuned_acc * 100)
    else:
        logger.info("Tuned model: %.1f%% — use Accept/Reject in admin panel", tuned_acc * 100)

    return {
        "tuned_test_accuracy": tuned_acc,
        "current_test_accuracy": current_acc,
        "tuned_params": best_params,
        "status": "pending",
    }


def apply_tuned_model() -> dict[str, Any]:
    """Promote the candidate tuned model to active."""
    settings = get_settings()
    artifacts_dir = resolve_artifact_path(settings.model_path).parent
    candidate_model = artifacts_dir / "model_candidate.joblib"
    candidate_config = artifacts_dir / "feature_config_candidate.json"
    tuning_path = artifacts_dir / "tuning_result.json"

    if not candidate_model.exists():
        raise FileNotFoundError("No candidate model found. Run Tune Model first.")

    # Overwrite active model with candidate
    import shutil
    shutil.copy2(candidate_model, resolve_artifact_path(settings.model_path))
    shutil.copy2(candidate_config, resolve_artifact_path(settings.feature_config_path))

    # Update tuning status
    tuning_result = json.loads(tuning_path.read_text())
    tuning_result["status"] = "accepted"
    tuning_path.write_text(json.dumps(tuning_result, indent=2), encoding="utf-8")

    # Update training metadata
    metadata_path = resolve_artifact_path(settings.training_metadata_path)
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        metadata["tuned_params"] = tuning_result.get("best_params")
        metadata["test"]["full_model"]["accuracy"] = tuning_result.get("tuned_test_accuracy")
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Clean up candidate files
    candidate_model.unlink()
    candidate_config.unlink()

    logger.info("Tuned model accepted and promoted to active.")
    return {"status": "accepted", "accuracy": tuning_result.get("tuned_test_accuracy")}


def reject_tuned_model() -> dict[str, Any]:
    """Discard the candidate tuned model."""
    settings = get_settings()
    artifacts_dir = resolve_artifact_path(settings.model_path).parent
    candidate_model = artifacts_dir / "model_candidate.joblib"
    candidate_config = artifacts_dir / "feature_config_candidate.json"
    tuning_path = artifacts_dir / "tuning_result.json"

    if candidate_model.exists():
        candidate_model.unlink()
    if candidate_config.exists():
        candidate_config.unlink()

    if tuning_path.exists():
        tuning_result = json.loads(tuning_path.read_text())
        tuning_result["status"] = "rejected"
        tuning_path.write_text(json.dumps(tuning_result, indent=2), encoding="utf-8")

    logger.info("Tuned model rejected and discarded.")
    return {"status": "rejected"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the VLR prediction model.")
    parser.add_argument("--limit", type=int, default=None, help="Limit training rows for a quick smoke run.")
    parser.add_argument(
        "--min-train-months",
        type=int,
        default=6,
        help="Minimum number of initial months before the first validation fold.",
    )
    parser.add_argument(
        "--model",
        default="auto",
        choices=["auto", "xgboost", "hist_gradient_boosting"],
        help="Preferred model family.",
    )
    args = parser.parse_args()
    metadata = train_and_save(
        limit=args.limit,
        min_train_months=args.min_train_months,
        preferred_model=args.model,
    )
    print(
        json.dumps(
            {
                "model_version": metadata["model_version"],
                "model_type": metadata["model_type"],
                "rows": metadata["row_count"],
                "test_month": metadata["test"]["month"],
                "test_metrics": metadata["test"]["full_model"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

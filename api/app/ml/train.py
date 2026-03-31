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


def build_training_dataset(session: Session, *, limit: int | None = None) -> pd.DataFrame:
    """Compute feature rows for every resolved historical map."""
    records: list[dict[str, Any]] = []
    rows = load_training_rows(session, limit=limit)
    total = len(rows)
    logger.info("Computing features for %d maps...", total)

    for i, row in enumerate(rows):
        if (i + 1) % 500 == 0:
            logger.info("  %d/%d maps featurized...", i + 1, total)
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
) -> dict[str, Any]:
    """Train the model, evaluate it, and persist artifacts."""
    logger.info("Building training dataset...")
    with SyncSessionLocal() as session:
        dataset = build_training_dataset(session, limit=limit)
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

"""Model artifact loading and ad-hoc inference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.features import FEATURE_NAMES, compute_features


@dataclass(frozen=True)
class TeamLookup:
    id: int
    name: str


@dataclass(frozen=True)
class ModelBundle:
    model: Any
    feature_names: list[str]
    imputation_values: dict[str, float]
    metadata: dict[str, Any]
    model_version: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_artifact_path(raw_path: str) -> Path:
    """Resolve artifact paths against the repo root when given relative paths."""
    path = Path(raw_path)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return repo_root() / path


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _predict_probability(model: Any, vector: np.ndarray) -> float:
    if hasattr(model, "predict_proba"):
        return float(model.predict_proba(vector)[0][1])
    if hasattr(model, "decision_function"):
        score = float(model.decision_function(vector)[0])
        return float(1.0 / (1.0 + np.exp(-score)))
    raise TypeError("Loaded model does not support probability prediction.")


def _prepare_vector(
    features: dict[str, float | None],
    feature_names: list[str],
    imputation_values: dict[str, float],
) -> pd.DataFrame:
    ordered: list[float] = []
    for name in feature_names:
        value = features.get(name)
        if value is None:
            value = imputation_values.get(name, 0.0)
        ordered.append(float(value))
    return pd.DataFrame([ordered], columns=feature_names, dtype=float)


def _metadata_path() -> Path:
    return resolve_artifact_path(get_settings().training_metadata_path)


@lru_cache(maxsize=1)
def load_training_metadata() -> dict[str, Any]:
    path = _metadata_path()
    if not path.exists():
        raise FileNotFoundError("Training metadata not available")
    return _load_json(path)


@lru_cache(maxsize=1)
def load_model_bundle() -> ModelBundle:
    settings = get_settings()
    model_path = resolve_artifact_path(settings.model_path)
    feature_config_path = resolve_artifact_path(settings.feature_config_path)

    if not model_path.exists():
        raise FileNotFoundError("Model not available")
    if not feature_config_path.exists():
        raise FileNotFoundError("Model configuration not available")

    feature_config = _load_json(feature_config_path)
    metadata = load_training_metadata()

    feature_names = list(feature_config.get("feature_names", FEATURE_NAMES))
    imputation_values = {
        str(key): float(value)
        for key, value in feature_config.get("imputation_values", {}).items()
    }

    return ModelBundle(
        model=joblib.load(model_path),
        feature_names=feature_names,
        imputation_values=imputation_values,
        metadata=metadata,
        model_version=str(metadata.get("model_version", "unknown")),
    )


def clear_model_cache() -> None:
    load_model_bundle.cache_clear()
    load_training_metadata.cache_clear()


def resolve_team(
    session: Session,
    *,
    team_id: int | None = None,
    team_name: str | None = None,
) -> TeamLookup:
    """Resolve a team by id or by case-insensitive name."""
    if team_id is not None:
        row = session.execute(
            text("SELECT id, name FROM teams WHERE id = :team_id"),
            {"team_id": team_id},
        ).fetchone()
        if row is None:
            raise LookupError(f"Unknown team id: {team_id}")
        return TeamLookup(id=int(row[0]), name=str(row[1]))

    if not team_name:
        raise LookupError("Team name or team id is required.")

    exact = session.execute(
        text(
            """
            SELECT id, name
            FROM teams
            WHERE lower(trim(name)) = lower(trim(:team_name))
            LIMIT 1
            """
        ),
        {"team_name": team_name},
    ).fetchone()
    if exact is not None:
        return TeamLookup(id=int(exact[0]), name=str(exact[1]))

    rows = session.execute(
        text(
            """
            SELECT id, name
            FROM teams
            WHERE name ILIKE :pattern
            ORDER BY length(name), name
            LIMIT 2
            """
        ),
        {"pattern": f"%{team_name}%"},
    ).fetchall()
    if len(rows) == 1:
        row = rows[0]
        return TeamLookup(id=int(row[0]), name=str(row[1]))
    if len(rows) > 1:
        raise LookupError(f"Ambiguous team name: {team_name}")
    raise LookupError(f"Unknown team name: {team_name}")


def _check_vct_teams(session: Session, team1_id: int, team2_id: int) -> str | None:
    """Return a warning string if either team is not in the VCT tier 1/2 set."""
    from app.ml.train import load_vct_team_ids

    vct_ids = load_vct_team_ids(session)
    non_vct = []
    if team1_id not in vct_ids:
        non_vct.append("team1")
    if team2_id not in vct_ids:
        non_vct.append("team2")
    if non_vct:
        return f"Warning: {' and '.join(non_vct)} not in VCT tier 1/2. Prediction may be less accurate."
    return None


def predict_matchup(
    session: Session,
    *,
    team1_id: int,
    team2_id: int,
    map_name: str | None,
    match_date: datetime | None = None,
) -> dict[str, Any]:
    """Compute features and return a model probability for team 1."""
    if team1_id == team2_id:
        raise ValueError("team1 and team2 must be different teams.")

    bundle = load_model_bundle()
    cutoff = match_date or datetime.utcnow()
    features = compute_features(
        session,
        team1_id=team1_id,
        team2_id=team2_id,
        map_name=map_name,
        match_date=cutoff,
    )
    vector = _prepare_vector(features, bundle.feature_names, bundle.imputation_values)
    probability = _predict_probability(bundle.model, vector)
    warning = _check_vct_teams(session, team1_id, team2_id)
    result: dict[str, Any] = {
        "team1_win_prob": probability,
        "team2_win_prob": 1.0 - probability,
        "model_version": bundle.model_version,
        "match_date": cutoff,
    }
    if warning:
        result["warning"] = warning
    return result


def _get_common_maps(session: Session, team1_id: int, team2_id: int) -> list[str]:
    """Get maps both teams have played recently, ordered by combined games played."""
    rows = session.execute(
        text("""
            WITH team_maps AS (
                SELECT m.map_name, mt.team1_id AS tid, mt.team2_id AS tid2
                FROM maps m
                JOIN matches mt ON m.match_id = mt.id
                WHERE m.map_name IS NOT NULL
                  AND mt.date IS NOT NULL
                  AND mt.date > NOW() - INTERVAL '6 months'
                  AND (mt.team1_id IN (:t1, :t2) OR mt.team2_id IN (:t1, :t2))
            )
            SELECT map_name,
                   COUNT(*) FILTER (WHERE tid = :t1 OR tid2 = :t1) AS t1_games,
                   COUNT(*) FILTER (WHERE tid = :t2 OR tid2 = :t2) AS t2_games
            FROM team_maps
            GROUP BY map_name
            HAVING COUNT(*) FILTER (WHERE tid = :t1 OR tid2 = :t1) > 0
               AND COUNT(*) FILTER (WHERE tid = :t2 OR tid2 = :t2) > 0
            ORDER BY COUNT(*) DESC
        """),
        {"t1": team1_id, "t2": team2_id},
    ).fetchall()
    return [row[0] for row in rows]


def _bo3_score_probs(p1: float, p2: float, p3: float) -> dict[str, float]:
    """Analytical Bo3 score line probabilities from per-map win probs."""
    return {
        "2-0": p1 * p2,
        "2-1": p1 * (1 - p2) * p3 + (1 - p1) * p2 * p3,
        "0-2": (1 - p1) * (1 - p2),
        "1-2": p1 * (1 - p2) * (1 - p3) + (1 - p1) * p2 * (1 - p3),
    }


def predict_series(
    session: Session,
    *,
    team1_id: int,
    team2_id: int,
    match_date: datetime | None = None,
) -> dict[str, Any]:
    """Predict per-map probabilities and Bo3 score lines for a series."""
    if team1_id == team2_id:
        raise ValueError("team1 and team2 must be different teams.")

    bundle = load_model_bundle()
    cutoff = match_date or datetime.utcnow()

    # Get maps both teams play
    common_maps = _get_common_maps(session, team1_id, team2_id)
    if len(common_maps) < 3:
        # Fall back to most common maps in the DB
        rows = session.execute(text("""
            SELECT map_name, COUNT(*) AS cnt
            FROM maps
            WHERE map_name IS NOT NULL
            GROUP BY map_name
            ORDER BY cnt DESC
            LIMIT 7
        """)).fetchall()
        all_maps = [r[0] for r in rows]
        # Fill in missing maps
        for m in all_maps:
            if m not in common_maps:
                common_maps.append(m)
            if len(common_maps) >= 3:
                break

    # Predict each map
    map_predictions = []
    for map_name in common_maps:
        features = compute_features(
            session,
            team1_id=team1_id,
            team2_id=team2_id,
            map_name=map_name,
            match_date=cutoff,
        )
        vector = _prepare_vector(features, bundle.feature_names, bundle.imputation_values)
        prob = _predict_probability(bundle.model, vector)
        map_predictions.append({
            "map_name": map_name,
            "team1_win_prob": prob,
            "team2_win_prob": 1.0 - prob,
        })

    # Use top 3 maps for Bo3 score lines
    top3 = map_predictions[:3] if len(map_predictions) >= 3 else map_predictions
    if len(top3) == 3:
        score_probs = _bo3_score_probs(
            top3[0]["team1_win_prob"],
            top3[1]["team1_win_prob"],
            top3[2]["team1_win_prob"],
        )
    elif len(top3) == 2:
        # Bo2-ish: only two maps
        p1, p2 = top3[0]["team1_win_prob"], top3[1]["team1_win_prob"]
        score_probs = {"2-0": p1 * p2, "0-2": (1 - p1) * (1 - p2),
                       "1-1": p1 * (1 - p2) + (1 - p1) * p2}
    else:
        score_probs = None

    # Overall series win prob from score lines
    if score_probs and "2-0" in score_probs and "2-1" in score_probs:
        series_win_prob = score_probs["2-0"] + score_probs["2-1"]
    else:
        series_win_prob = None

    return {
        "map_predictions": map_predictions,
        "score_probs": score_probs,
        "series_win_prob": series_win_prob,
        "model_version": bundle.model_version,
        "match_date": cutoff,
    }

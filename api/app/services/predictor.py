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
    return {
        "team1_win_prob": probability,
        "team2_win_prob": 1.0 - probability,
        "model_version": bundle.model_version,
        "match_date": cutoff,
    }

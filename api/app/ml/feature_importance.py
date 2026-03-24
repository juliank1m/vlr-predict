"""Feature-importance helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance


def rank_feature_importance(
    model: Any,
    feature_names: list[str],
    *,
    X_reference: pd.DataFrame | None = None,
    y_reference: pd.Series | np.ndarray | None = None,
    top_k: int | None = None,
) -> list[dict[str, float | str]]:
    """Return feature importance rankings for the fitted model."""
    importances: np.ndarray | None = None

    if hasattr(model, "feature_importances_"):
        raw = np.asarray(model.feature_importances_, dtype=float)
        if raw.shape[0] == len(feature_names):
            importances = raw
    elif hasattr(model, "coef_"):
        raw = np.asarray(model.coef_, dtype=float).reshape(-1)
        if raw.shape[0] == len(feature_names):
            importances = np.abs(raw)

    if importances is None:
        if X_reference is None or y_reference is None:
            raise ValueError("Reference data required for permutation importance.")

        sample = min(len(X_reference), 2000)
        X_eval = X_reference.iloc[:sample]
        y_eval = np.asarray(y_reference)[:sample]
        result = permutation_importance(
            model,
            X_eval,
            y_eval,
            scoring="neg_log_loss",
            n_repeats=5,
            random_state=42,
        )
        importances = np.asarray(result.importances_mean, dtype=float)

    ranked = sorted(
        (
            {
                "feature": name,
                "importance": float(score),
            }
            for name, score in zip(feature_names, importances, strict=True)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )
    return ranked if top_k is None else ranked[:top_k]


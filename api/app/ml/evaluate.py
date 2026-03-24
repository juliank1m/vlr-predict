"""Evaluation helpers for model training and reporting."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss


def clip_probabilities(probabilities: np.ndarray | list[float]) -> np.ndarray:
    """Clip probabilities away from 0 and 1 for stable metric computation."""
    probs = np.asarray(probabilities, dtype=float)
    return np.clip(probs, 1e-6, 1.0 - 1e-6)


def summarize_binary_predictions(
    y_true: np.ndarray | list[int],
    probabilities: np.ndarray | list[float],
) -> dict[str, float]:
    """Return common binary classification metrics for probability forecasts."""
    target = np.asarray(y_true, dtype=int)
    probs = clip_probabilities(probabilities)
    preds = (probs >= 0.5).astype(int)
    return {
        "log_loss": float(log_loss(target, probs, labels=[0, 1])),
        "brier_score": float(brier_score_loss(target, probs)),
        "accuracy": float(accuracy_score(target, preds)),
    }


def calibration_curve_data(
    y_true: np.ndarray | list[int],
    probabilities: np.ndarray | list[float],
    *,
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Compute fixed-width calibration bins."""
    target = np.asarray(y_true, dtype=int)
    probs = clip_probabilities(probabilities)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.digitize(probs, edges[1:-1], right=False)

    bins: list[dict[str, Any]] = []
    for idx in range(n_bins):
        mask = bin_ids == idx
        count = int(mask.sum())
        lower = float(edges[idx])
        upper = float(edges[idx + 1])
        if count == 0:
            bins.append(
                {
                    "bin": idx,
                    "range": [lower, upper],
                    "count": 0,
                    "avg_predicted": None,
                    "actual_rate": None,
                }
            )
            continue

        bins.append(
            {
                "bin": idx,
                "range": [lower, upper],
                "count": count,
                "avg_predicted": float(probs[mask].mean()),
                "actual_rate": float(target[mask].mean()),
            }
        )
    return bins


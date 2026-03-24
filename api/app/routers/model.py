"""Model performance endpoints."""

from fastapi import APIRouter, HTTPException

from app.services.predictor import load_training_metadata

router = APIRouter()


@router.get("/accuracy")
async def get_model_accuracy():
    """Return rolling accuracy metrics."""
    try:
        metadata = load_training_metadata()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    folds = metadata.get("temporal_cv", {}).get("folds", [])
    rolling = [
        {
            "month": fold["validate_month"],
            "accuracy": fold["full_model"]["accuracy"],
            "log_loss": fold["full_model"]["log_loss"],
            "brier_score": fold["full_model"]["brier_score"],
        }
        for fold in folds
    ]
    return {
        "model_version": metadata.get("model_version"),
        "model_type": metadata.get("model_type"),
        "trained_at": metadata.get("trained_at"),
        "summary": metadata.get("temporal_cv", {}).get("summary", {}),
        "rolling": rolling,
        "test": metadata.get("test", {}),
        "warning": metadata.get("warning"),
    }


@router.get("/features")
async def get_feature_importance():
    """Return feature importance rankings."""
    try:
        metadata = load_training_metadata()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "model_version": metadata.get("model_version"),
        "model_type": metadata.get("model_type"),
        "trained_at": metadata.get("trained_at"),
        "features": metadata.get("feature_importances", []),
    }

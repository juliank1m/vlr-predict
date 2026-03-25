"""Prediction endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from app.database import SyncSessionLocal
from app.rate_limit import limiter
from app.services.predictor import predict_matchup, resolve_team

router = APIRouter()
adhoc_router = APIRouter()


class PredictionRequest(BaseModel):
    """Ad-hoc prediction request body."""

    team1: str | None = Field(default=None, max_length=200)
    team2: str | None = Field(default=None, max_length=200)
    team1_id: int | None = Field(default=None, ge=1)
    team2_id: int | None = Field(default=None, ge=1)
    map_name: str | None = Field(default=None, max_length=50)
    match_date: datetime | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_identifiers(self) -> PredictionRequest:
        if (self.team1_id is None) == (self.team1 is None):
            raise ValueError("Provide exactly one of team1 or team1_id.")
        if (self.team2_id is None) == (self.team2 is None):
            raise ValueError("Provide exactly one of team2 or team2_id.")
        return self


def _serialize_prediction_rows(rows: list[object]) -> list[dict[str, object]]:
    return [
        {
            "id": int(row["id"]),
            "match_id": row["match_id"],
            "map_id": row["map_id"],
            "match_date": row["match_date"],
            "team1_id": int(row["team1_id"]),
            "team1_name": row["team1_name"],
            "team2_id": int(row["team2_id"]),
            "team2_name": row["team2_name"],
            "map_name": row["map_name"],
            "team1_win_prob": float(row["team1_win_prob"]),
            "team2_win_prob": 1.0 - float(row["team1_win_prob"]),
            "model_version": row["model_version"],
            "predicted_at": row["predicted_at"],
            "correct": row["correct"],
        }
        for row in rows
    ]


def _get_upcoming_predictions_sync(limit: int) -> dict[str, object]:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    p.id,
                    p.match_id,
                    p.map_id,
                    mt.date AS match_date,
                    p.team1_id,
                    t1.name AS team1_name,
                    p.team2_id,
                    t2.name AS team2_name,
                    p.map_name,
                    p.team1_win_prob,
                    p.model_version,
                    p.predicted_at,
                    p.correct
                FROM predictions p
                JOIN teams t1 ON t1.id = p.team1_id
                JOIN teams t2 ON t2.id = p.team2_id
                LEFT JOIN matches mt ON mt.id = p.match_id
                WHERE p.correct IS NULL
                ORDER BY mt.date ASC NULLS LAST, p.predicted_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return {"items": _serialize_prediction_rows(rows), "count": len(rows)}


def _get_prediction_history_sync(limit: int) -> dict[str, object]:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    p.id,
                    p.match_id,
                    p.map_id,
                    mt.date AS match_date,
                    p.team1_id,
                    t1.name AS team1_name,
                    p.team2_id,
                    t2.name AS team2_name,
                    p.map_name,
                    p.team1_win_prob,
                    p.model_version,
                    p.predicted_at,
                    p.correct
                FROM predictions p
                JOIN teams t1 ON t1.id = p.team1_id
                JOIN teams t2 ON t2.id = p.team2_id
                LEFT JOIN matches mt ON mt.id = p.match_id
                WHERE p.correct IS NOT NULL
                ORDER BY p.predicted_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        accuracy = session.execute(
            text(
                """
                SELECT AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END)
                FROM predictions
                WHERE correct IS NOT NULL
                """
            )
        ).scalar()

    return {
        "items": _serialize_prediction_rows(rows),
        "summary": {
            "count": len(rows),
            "accuracy": float(accuracy) if accuracy is not None else None,
        },
    }


def _predict_sync(payload: PredictionRequest) -> dict[str, object]:
    with SyncSessionLocal() as session:
        team1 = resolve_team(session, team_id=payload.team1_id, team_name=payload.team1)
        team2 = resolve_team(session, team_id=payload.team2_id, team_name=payload.team2)
        result = predict_matchup(
            session,
            team1_id=team1.id,
            team2_id=team2.id,
            map_name=payload.map_name.strip() if payload.map_name else None,
            match_date=payload.match_date,
        )

    return {
        "team1": {"id": team1.id, "name": team1.name},
        "team2": {"id": team2.id, "name": team2.name},
        "map_name": payload.map_name,
        "match_date": result["match_date"],
        "team1_win_prob": result["team1_win_prob"],
        "team2_win_prob": result["team2_win_prob"],
        "model_version": result["model_version"],
    }


@router.get("/upcoming")
async def get_upcoming_predictions(limit: int = Query(default=25, ge=1, le=100)):
    """Return predictions for upcoming matches."""
    return await run_in_threadpool(_get_upcoming_predictions_sync, limit)


@router.get("/history")
async def get_prediction_history(limit: int = Query(default=100, ge=1, le=500)):
    """Return past predictions with accuracy."""
    return await run_in_threadpool(_get_prediction_history_sync, limit)


@adhoc_router.post("/predict")
@limiter.limit("10/minute")
async def predict(request: Request, payload: PredictionRequest):
    """Return an ad-hoc team1 win probability for a matchup."""
    try:
        return await run_in_threadpool(_predict_sync, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

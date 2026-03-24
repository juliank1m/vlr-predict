"""API tests for prediction and model endpoints."""

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from app.main import app
from app.routers import matches, model, predictions, teams


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_model_accuracy_endpoint_returns_metadata_projection(client, monkeypatch):
    monkeypatch.setattr(
        model,
        "load_training_metadata",
        lambda: {
            "model_version": "xgb_v1",
            "model_type": "xgboost",
            "trained_at": "2026-03-24T00:00:00+00:00",
            "temporal_cv": {
                "summary": {"full_model": {"accuracy": 0.63, "log_loss": 0.61, "brier_score": 0.21}},
                "folds": [
                    {
                        "validate_month": "2025-01-01",
                        "full_model": {"accuracy": 0.62, "log_loss": 0.6, "brier_score": 0.2},
                    }
                ],
            },
            "test": {"month": "2026-02-01"},
        },
    )

    response = client.get("/api/model/accuracy")
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "xgb_v1"
    assert body["rolling"][0]["month"] == "2025-01-01"
    assert body["summary"]["full_model"]["accuracy"] == 0.63


def test_model_features_endpoint_returns_rankings(client, monkeypatch):
    monkeypatch.setattr(
        model,
        "load_training_metadata",
        lambda: {
            "model_version": "xgb_v1",
            "model_type": "xgboost",
            "trained_at": "2026-03-24T00:00:00+00:00",
            "feature_importances": [
                {"feature": "elo_diff", "importance": 0.31},
                {"feature": "rating_diff_10", "importance": 0.14},
            ],
        },
    )

    response = client.get("/api/model/features")
    assert response.status_code == 200
    body = response.json()
    assert body["features"][0]["feature"] == "elo_diff"
    assert body["features"][1]["importance"] == 0.14


def test_predict_endpoint_returns_prediction_payload(client, monkeypatch):
    monkeypatch.setattr(
        predictions,
        "_predict_sync",
        lambda payload: {
            "team1": {"id": 1, "name": "Sentinels"},
            "team2": {"id": 2, "name": "Gen.G"},
            "map_name": payload.map_name,
            "match_date": "2026-03-24T12:00:00",
            "team1_win_prob": 0.64,
            "team2_win_prob": 0.36,
            "model_version": "xgb_v1",
            "features": {"elo_diff": 42.0},
        },
    )

    response = client.post(
        "/api/predict",
        json={"team1": "Sentinels", "team2": "Gen.G", "map_name": "Ascent"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["team1"]["name"] == "Sentinels"
    assert body["team1_win_prob"] == 0.64
    assert body["features"]["elo_diff"] == 42.0


def test_predict_endpoint_surfaces_missing_model(client, monkeypatch):
    def _raise(_: object) -> dict[str, object]:
        raise FileNotFoundError("model artifact missing")

    monkeypatch.setattr(predictions, "_predict_sync", _raise)

    response = client.post(
        "/api/predict",
        json={"team1_id": 1, "team2_id": 2, "map_name": "Bind"},
    )
    assert response.status_code == 503
    assert "model artifact missing" in response.json()["detail"]


def test_prediction_history_endpoint_returns_summary(client, monkeypatch):
    monkeypatch.setattr(
        predictions,
        "_get_prediction_history_sync",
        lambda limit: {
            "items": [{"id": 7, "team1_name": "A", "team2_name": "B", "correct": True}],
            "summary": {"count": 1, "accuracy": 1.0},
        },
    )

    response = client.get("/api/predictions/history?limit=5")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["accuracy"] == 1.0
    assert body["items"][0]["id"] == 7


def test_matches_list_endpoint_uses_router_payload(client, monkeypatch):
    monkeypatch.setattr(
        matches,
        "_list_matches_sync",
        lambda page, page_size, resolved_only: {
            "items": [{"id": 10, "team1_name": "A", "team2_name": "B"}],
            "page": page,
            "page_size": page_size,
            "total": 1,
            "resolved_only": resolved_only,
        },
    )

    response = client.get("/api/matches?page=2&page_size=10&resolved_only=false")
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 10
    assert body["items"][0]["id"] == 10


def test_match_detail_returns_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(matches, "_get_match_sync", lambda match_id: None)

    response = client.get("/api/matches/404")
    assert response.status_code == 404
    assert "404" in response.json()["detail"]


def test_team_list_endpoint_returns_items(client, monkeypatch):
    monkeypatch.setattr(
        teams,
        "_list_teams_sync",
        lambda search, limit: {
            "items": [{"id": 1, "name": "Sentinels"}],
            "count": 1,
        },
    )

    response = client.get("/api/teams?search=sen")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["name"] == "Sentinels"


def test_team_players_endpoint_returns_team_context(client, monkeypatch):
    monkeypatch.setattr(
        teams,
        "_get_team_sync",
        lambda team_id: {"id": team_id, "name": "Sentinels"},
    )
    monkeypatch.setattr(
        teams,
        "_get_team_players_sync",
        lambda team_id: [{"id": 99, "name": "zekken", "is_current": True}],
    )

    response = client.get("/api/teams/1/players")
    assert response.status_code == 200
    body = response.json()
    assert body["team_name"] == "Sentinels"
    assert body["players"][0]["name"] == "zekken"

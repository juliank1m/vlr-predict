"""Integration test for /api/predictions/upcoming median odds + EV.

Pre-seeds teams + matches + predictions + odds in the real DB, then hits the
endpoint via TestClient. Requires a local Postgres (docker compose up -d db).
"""

from datetime import datetime, timedelta

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import SyncSessionLocal
from app.main import app

# Distinct id range to avoid colliding with other tests.
TEAM1_ID = 999_810_001
TEAM2_ID = 999_810_002
MATCH_WITH_ODDS = 999_810_001
MATCH_WITHOUT_ODDS = 999_810_002
MATCH_IDS = [MATCH_WITH_ODDS, MATCH_WITHOUT_ODDS]
TEAM_IDS = [TEAM1_ID, TEAM2_ID]


def _db_available() -> bool:
    try:
        with SyncSessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="Local Postgres is not available",
)


def _cleanup() -> None:
    with SyncSessionLocal() as db:
        db.execute(
            text("DELETE FROM odds WHERE match_id = ANY(:ids)"),
            {"ids": MATCH_IDS},
        )
        db.execute(
            text("DELETE FROM predictions WHERE match_id = ANY(:ids)"),
            {"ids": MATCH_IDS},
        )
        db.execute(
            text("DELETE FROM matches WHERE id = ANY(:ids)"),
            {"ids": MATCH_IDS},
        )
        db.execute(
            text("DELETE FROM teams WHERE id = ANY(:ids)"),
            {"ids": TEAM_IDS},
        )
        db.commit()


@pytest.fixture
def seeded_state():
    _cleanup()
    future = datetime.utcnow() + timedelta(days=2)
    later = datetime.utcnow() + timedelta(days=3)

    with SyncSessionLocal() as db:
        db.execute(
            text("INSERT INTO teams (id, name) VALUES (:id, :n)"),
            {"id": TEAM1_ID, "n": "Upcoming Odds Team A"},
        )
        db.execute(
            text("INSERT INTO teams (id, name) VALUES (:id, :n)"),
            {"id": TEAM2_ID, "n": "Upcoming Odds Team B"},
        )

        # Match with odds.
        db.execute(
            text("""
                INSERT INTO matches (
                    id, team1_id, team2_id, url, date,
                    team1_score, team2_score, winner_id
                )
                VALUES (
                    :id, :t1, :t2, :url, :date,
                    NULL, NULL, NULL
                )
            """),
            {
                "id": MATCH_WITH_ODDS,
                "t1": TEAM1_ID,
                "t2": TEAM2_ID,
                "url": "https://www.vlr.gg/999810001/upcoming-odds-a",
                "date": future,
            },
        )
        # Match without odds (different date so ordering is deterministic).
        db.execute(
            text("""
                INSERT INTO matches (
                    id, team1_id, team2_id, url, date,
                    team1_score, team2_score, winner_id
                )
                VALUES (
                    :id, :t1, :t2, :url, :date,
                    NULL, NULL, NULL
                )
            """),
            {
                "id": MATCH_WITHOUT_ODDS,
                "t1": TEAM1_ID,
                "t2": TEAM2_ID,
                "url": "https://www.vlr.gg/999810002/upcoming-odds-b",
                "date": later,
            },
        )

        # Predictions: team1_win_prob = 0.6 for both.
        db.execute(
            text("""
                INSERT INTO predictions (
                    match_id, team1_id, team2_id,
                    team1_win_prob, model_version, predicted_at, correct
                )
                VALUES (
                    :mid, :t1, :t2, 0.6, 'test_v1', :now, NULL
                )
            """),
            {
                "mid": MATCH_WITH_ODDS,
                "t1": TEAM1_ID,
                "t2": TEAM2_ID,
                "now": datetime.utcnow(),
            },
        )
        db.execute(
            text("""
                INSERT INTO predictions (
                    match_id, team1_id, team2_id,
                    team1_win_prob, model_version, predicted_at, correct
                )
                VALUES (
                    :mid, :t1, :t2, 0.6, 'test_v1', :now, NULL
                )
            """),
            {
                "mid": MATCH_WITHOUT_ODDS,
                "t1": TEAM1_ID,
                "t2": TEAM2_ID,
                "now": datetime.utcnow(),
            },
        )

        # Two odds rows for MATCH_WITH_ODDS — different decimals so the
        # median ends up exactly between the two implied probabilities.
        now = datetime.utcnow()
        db.execute(
            text("""
                INSERT INTO odds (
                    match_id, bookmaker, team1_decimal,
                    team2_decimal, fetched_at
                )
                VALUES (:mid, :bk, :t1d, :t2d, :ts)
            """),
            {
                "mid": MATCH_WITH_ODDS,
                "bk": "bookA",
                "t1d": 1.5,
                "t2d": 2.6,
                "ts": now,
            },
        )
        db.execute(
            text("""
                INSERT INTO odds (
                    match_id, bookmaker, team1_decimal,
                    team2_decimal, fetched_at
                )
                VALUES (:mid, :bk, :t1d, :t2d, :ts)
            """),
            {
                "mid": MATCH_WITH_ODDS,
                "bk": "bookB",
                "t1d": 1.7,
                "t2d": 2.4,
                "ts": now,
            },
        )

        db.commit()

    try:
        yield
    finally:
        _cleanup()


def _find_item(items: list[dict], match_id: int) -> dict:
    for it in items:
        if it.get("match_id") == match_id:
            return it
    raise AssertionError(f"match_id {match_id} not in upcoming response")


def test_upcoming_includes_median_implied_and_ev(seeded_state):
    expected_t1 = (1.0 / 1.5 + 1.0 / 1.7) / 2  # exact median of 2 values
    expected_t2 = (1.0 / 2.6 + 1.0 / 2.4) / 2

    with TestClient(app) as client:
        resp = client.get("/api/predictions/upcoming?limit=100")
    assert resp.status_code == 200
    body = resp.json()

    item = _find_item(body["items"], MATCH_WITH_ODDS)

    assert item["team1_implied"] == pytest.approx(expected_t1, abs=1e-6)
    assert item["team2_implied"] == pytest.approx(expected_t2, abs=1e-6)
    assert item["book_count"] == 2
    assert item["team1_ev"] == pytest.approx(0.6 / expected_t1 - 1, abs=1e-6)
    assert item["team2_ev"] == pytest.approx(0.4 / expected_t2 - 1, abs=1e-6)


def test_upcoming_handles_missing_odds(seeded_state):
    with TestClient(app) as client:
        resp = client.get("/api/predictions/upcoming?limit=100")
    assert resp.status_code == 200
    body = resp.json()

    item = _find_item(body["items"], MATCH_WITHOUT_ODDS)

    assert item["team1_implied"] is None
    assert item["team2_implied"] is None
    assert item["team1_ev"] is None
    assert item["team2_ev"] is None
    assert item["book_count"] == 0

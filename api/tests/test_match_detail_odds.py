"""Integration test for /api/matches/{id} odds payload.

Pre-seeds teams + a match + odds rows in the real DB, then hits the
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
TEAM1_ID = 999_820_001
TEAM2_ID = 999_820_002
MATCH_WITH_ODDS = 999_820_001
MATCH_WITHOUT_ODDS = 999_820_002
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
            {"id": TEAM1_ID, "n": "Match Detail Odds Team A"},
        )
        db.execute(
            text("INSERT INTO teams (id, name) VALUES (:id, :n)"),
            {"id": TEAM2_ID, "n": "Match Detail Odds Team B"},
        )

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
                "url": "https://www.vlr.gg/999820001/match-detail-odds-a",
                "date": future,
            },
        )
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
                "url": "https://www.vlr.gg/999820002/match-detail-odds-b",
                "date": later,
            },
        )

        now = datetime.utcnow()
        # Insert in non-alphabetical order to verify ORDER BY works.
        for bk, t1d, t2d in [
            ("thunderpick", 1.5, 2.6),
            ("bookA", 1.7, 2.4),
            ("midbook", 1.6, 2.5),
        ]:
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
                    "bk": bk,
                    "t1d": t1d,
                    "t2d": t2d,
                    "ts": now,
                },
            )

        db.commit()

    try:
        yield
    finally:
        _cleanup()


def test_match_detail_includes_odds_array_sorted_by_bookmaker(seeded_state):
    with TestClient(app) as client:
        resp = client.get(f"/api/matches/{MATCH_WITH_ODDS}")
    assert resp.status_code == 200
    body = resp.json()

    assert "odds" in body
    assert isinstance(body["odds"], list)
    assert len(body["odds"]) == 3

    bookmakers = [row["bookmaker"] for row in body["odds"]]
    assert bookmakers == sorted(bookmakers)
    assert bookmakers == ["bookA", "midbook", "thunderpick"]

    for row in body["odds"]:
        assert set(row.keys()) >= {
            "bookmaker",
            "team1_decimal",
            "team2_decimal",
            "fetched_at",
        }
        assert isinstance(row["team1_decimal"], float)
        assert isinstance(row["team2_decimal"], float)
        assert row["fetched_at"] is not None

    by_bk = {row["bookmaker"]: row for row in body["odds"]}
    assert by_bk["thunderpick"]["team1_decimal"] == pytest.approx(1.5)
    assert by_bk["thunderpick"]["team2_decimal"] == pytest.approx(2.6)
    assert by_bk["bookA"]["team1_decimal"] == pytest.approx(1.7)
    assert by_bk["midbook"]["team2_decimal"] == pytest.approx(2.5)


def test_match_detail_returns_empty_odds_list_when_none(seeded_state):
    with TestClient(app) as client:
        resp = client.get(f"/api/matches/{MATCH_WITHOUT_ODDS}")
    assert resp.status_code == 200
    body = resp.json()

    assert "odds" in body
    assert body["odds"] == []

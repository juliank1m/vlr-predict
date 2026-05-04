"""Integration test for refresh_odds_for_upcoming.

Re-fetches the detail page for every upcoming match in the DB and upserts
odds rows only — does NOT insert new matches or predictions.

Requires a local Postgres (docker compose up -d db). The test mocks _fetch
so no network is needed, but it does write to / read from the real DB.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import SyncSessionLocal
from app.services.scraper import refresh_odds_for_upcoming

MATCH_FIXTURE = Path(__file__).parent / "fixtures" / "vlr_upcoming_match.html"

# Use a distinct id range to avoid colliding with other tests.
TEAM1_ID = 999_800_001
TEAM2_ID = 999_800_002
MATCH1_ID = 999_800_001
MATCH2_ID = 999_800_002
MATCH_IDS = [MATCH1_ID, MATCH2_ID]
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
def seeded_upcoming_state():
    """Seed two teams + two upcoming matches; pre-insert one stale odds row.

    Also temporarily NULLs out the ``url`` column on every OTHER upcoming
    match in the DB so the function under test only sees our seeded rows.
    Restored on teardown.
    """
    _cleanup()

    future = datetime.utcnow() + timedelta(days=2)
    stale_fetched = datetime.utcnow() - timedelta(days=7)

    # Snapshot any other currently-upcoming matches so we can restore their
    # urls after the test. The SELECT mirrors the function's WHERE clause.
    with SyncSessionLocal() as db:
        other_rows = db.execute(text("""
            SELECT id, url
            FROM matches
            WHERE winner_id IS NULL
              AND url IS NOT NULL
              AND (date IS NULL OR date >= NOW())
        """)).fetchall()
        other_url_snapshot = [(r.id, r.url) for r in other_rows]
        if other_url_snapshot:
            db.execute(
                text("""
                    UPDATE matches SET url = NULL
                    WHERE id = ANY(:ids)
                """),
                {"ids": [r.id for r in other_rows]},
            )
        db.commit()

    with SyncSessionLocal() as db:
        db.execute(
            text("INSERT INTO teams (id, name) VALUES (:id, :n)"),
            {"id": TEAM1_ID, "n": "Refresh Test Team A"},
        )
        db.execute(
            text("INSERT INTO teams (id, name) VALUES (:id, :n)"),
            {"id": TEAM2_ID, "n": "Refresh Test Team B"},
        )

        # Upcoming match #1 — has a stale pre-existing odds row.
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
                "id": MATCH1_ID,
                "t1": TEAM1_ID,
                "t2": TEAM2_ID,
                "url": "https://www.vlr.gg/999800001/refresh-test-a",
                "date": future,
            },
        )
        # Upcoming match #2 — no odds yet.
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
                "id": MATCH2_ID,
                "t1": TEAM2_ID,
                "t2": TEAM1_ID,
                "url": "https://www.vlr.gg/999800002/refresh-test-b",
                "date": None,  # NULL date counts as upcoming
            },
        )

        # Stale odds row for match 1 — pick a bookmaker that exists in the
        # fixture so the upsert path actually fires UPDATE.
        db.execute(
            text("""
                INSERT INTO odds (
                    match_id, bookmaker, team1_decimal,
                    team2_decimal, fetched_at
                )
                VALUES (:mid, :bk, :t1d, :t2d, :ts)
            """),
            {
                "mid": MATCH1_ID,
                "bk": "thunderpick",
                "t1d": 9.99,  # obviously-stale value
                "t2d": 9.99,
                "ts": stale_fetched,
            },
        )
        db.commit()

    yield {
        "match_ids": MATCH_IDS,
        "stale_fetched_at": stale_fetched,
        "stale_decimal": 9.99,
    }

    _cleanup()

    # Restore the urls we cleared on other upcoming matches.
    if other_url_snapshot:
        with SyncSessionLocal() as db:
            for mid, url in other_url_snapshot:
                db.execute(
                    text("UPDATE matches SET url = :u WHERE id = :id"),
                    {"u": url, "id": mid},
                )
            db.commit()


def test_refresh_odds_for_upcoming_upserts_only(seeded_upcoming_state):
    match_soup = BeautifulSoup(MATCH_FIXTURE.read_text(), "html.parser")

    with patch(
        "app.services.scraper._fetch",
        return_value=match_soup,
    ), patch(
        "app.services.scraper.time.sleep",
        return_value=None,
    ):
        result = refresh_odds_for_upcoming()

    odds_per_match = 4  # known from earlier scraper-betting tests / fixture
    assert result["matches_refreshed"] == 2

    with SyncSessionLocal() as db:
        odds_count = db.execute(
            text("SELECT COUNT(*) FROM odds WHERE match_id = ANY(:ids)"),
            {"ids": MATCH_IDS},
        ).scalar()
        # No new matches should appear beyond the two we seeded.
        match_count = db.execute(
            text("SELECT COUNT(*) FROM matches WHERE id = ANY(:ids)"),
            {"ids": MATCH_IDS},
        ).scalar()
        # No predictions should be created.
        pred_count = db.execute(
            text("SELECT COUNT(*) FROM predictions WHERE match_id = ANY(:ids)"),
            {"ids": MATCH_IDS},
        ).scalar()
        # The stale ggbet row for match 1 should now reflect fixture values.
        stale_row = db.execute(
            text("""
                SELECT team1_decimal, team2_decimal, fetched_at
                FROM odds
                WHERE match_id = :mid AND bookmaker = 'thunderpick'
            """),
            {"mid": MATCH1_ID},
        ).fetchone()

    assert odds_count == 2 * odds_per_match
    assert match_count == 2
    assert pred_count == 0

    assert stale_row is not None
    new_t1, new_t2, new_fetched = stale_row
    # UPSERT — the stale 9.99/9.99 must have been replaced.
    assert float(new_t1) != 9.99
    assert float(new_t2) != 9.99
    assert new_fetched > seeded_upcoming_state["stale_fetched_at"]

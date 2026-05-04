"""Integration test for scrape_upcoming_matches.

Requires a local Postgres (docker compose up -d db) with migrations applied.
The test mocks _fetch and predict_matchup so no network or model artifact is
needed, but it does write to / read from the real DB.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import SyncSessionLocal
from app.services.scraper import _parse_schedule_page, scrape_upcoming_matches

SCHEDULE = Path(__file__).parent / "fixtures" / "vlr_schedule_page.html"
MATCH = Path(__file__).parent / "fixtures" / "vlr_upcoming_match.html"


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


def _fake_fetch_factory(schedule_soup, match_soup):
    def fake_fetch(_session, url):
        if url.endswith("/matches"):
            return schedule_soup
        return match_soup

    return fake_fetch


@pytest.fixture
def seeded_schedule_state():
    """Pre-seed teams from the schedule fixture and clear leftover test rows.

    Yields the list of (team1, team2) name pairs we expect to land. Cleans up
    after the test by deleting the inserted upcoming-match rows (and their
    cascaded odds/predictions) so re-runs are idempotent.
    """
    schedule_soup = BeautifulSoup(SCHEDULE.read_text(), "html.parser")
    rows = _parse_schedule_page(schedule_soup)
    valid_pairs = [
        (r["match_id"], r["team1_name"], r["team2_name"])
        for r in rows
        if r["team1_name"] != "TBD" and r["team2_name"] != "TBD"
    ][:2]
    assert valid_pairs, "fixture should have at least one non-TBD pair"

    match_ids = [mid for (mid, _, _) in valid_pairs]
    names = {n for (_, t1, t2) in valid_pairs for n in (t1, t2)}

    with SyncSessionLocal() as db:
        # Cleanup: remove any leftover rows for these schedule match IDs
        db.execute(
            text("DELETE FROM predictions WHERE match_id = ANY(:ids)"),
            {"ids": match_ids},
        )
        db.execute(
            text("DELETE FROM odds WHERE match_id = ANY(:ids)"),
            {"ids": match_ids},
        )
        db.execute(
            text("DELETE FROM matches WHERE id = ANY(:ids)"),
            {"ids": match_ids},
        )
        # Also remove any stale 'test' model_version predictions
        db.execute(
            text("DELETE FROM predictions WHERE model_version = 'test'")
        )
        for name in names:
            db.execute(
                text(
                    "INSERT INTO teams (name) VALUES (:n) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"n": name},
            )
        db.commit()

    yield valid_pairs

    # Teardown: remove rows we created in this test
    with SyncSessionLocal() as db:
        db.execute(
            text("DELETE FROM predictions WHERE match_id = ANY(:ids)"),
            {"ids": match_ids},
        )
        db.execute(
            text("DELETE FROM odds WHERE match_id = ANY(:ids)"),
            {"ids": match_ids},
        )
        db.execute(
            text("DELETE FROM matches WHERE id = ANY(:ids)"),
            {"ids": match_ids},
        )
        db.execute(
            text("DELETE FROM predictions WHERE model_version = 'test'")
        )
        db.commit()


def test_scrape_upcoming_inserts_match_odds_and_prediction(seeded_schedule_state):
    schedule_soup = BeautifulSoup(SCHEDULE.read_text(), "html.parser")
    match_soup = BeautifulSoup(MATCH.read_text(), "html.parser")

    seeded_pairs = seeded_schedule_state
    seeded_ids = [mid for (mid, _, _) in seeded_pairs]

    with patch(
        "app.services.scraper._fetch",
        side_effect=_fake_fetch_factory(schedule_soup, match_soup),
    ), patch(
        "app.services.scraper.predict_matchup",
        return_value={
            "team1_win_prob": 0.55,
            "team2_win_prob": 0.45,
            "model_version": "test",
            "match_date": None,
        },
    ), patch(
        "app.services.scraper.time.sleep",
        return_value=None,
    ):
        result = scrape_upcoming_matches()

    assert result["new_matches"] >= len(seeded_pairs)
    assert result["odds_rows"] >= len(seeded_pairs)
    assert result["predictions"] >= len(seeded_pairs)

    with SyncSessionLocal() as db:
        match_count = db.execute(
            text("SELECT COUNT(*) FROM matches WHERE id = ANY(:ids)"),
            {"ids": seeded_ids},
        ).scalar()
        odds_count = db.execute(
            text("SELECT COUNT(*) FROM odds WHERE match_id = ANY(:ids)"),
            {"ids": seeded_ids},
        ).scalar()
        pred_count = db.execute(
            text(
                "SELECT COUNT(*) FROM predictions "
                "WHERE model_version = 'test' AND match_id = ANY(:ids)"
            ),
            {"ids": seeded_ids},
        ).scalar()

    assert match_count == len(seeded_pairs)
    # Each match has 4 odds rows in the fixture
    assert odds_count >= len(seeded_pairs)
    assert pred_count == len(seeded_pairs)


def test_scrape_upcoming_is_idempotent(seeded_schedule_state):
    """Running twice should not double-insert matches or predictions."""
    schedule_soup = BeautifulSoup(SCHEDULE.read_text(), "html.parser")
    match_soup = BeautifulSoup(MATCH.read_text(), "html.parser")
    seeded_ids = [mid for (mid, _, _) in seeded_schedule_state]

    fake_fetch = _fake_fetch_factory(schedule_soup, match_soup)
    fake_predict = {
        "team1_win_prob": 0.55,
        "team2_win_prob": 0.45,
        "model_version": "test",
        "match_date": None,
    }

    with patch("app.services.scraper._fetch", side_effect=fake_fetch), \
         patch("app.services.scraper.predict_matchup", return_value=fake_predict), \
         patch("app.services.scraper.time.sleep", return_value=None):
        scrape_upcoming_matches()
        result2 = scrape_upcoming_matches()

    # Second run should insert no new matches (already in DB)
    assert result2["new_matches"] == 0
    # Predictions are only created for new matches
    assert result2["predictions"] == 0

    with SyncSessionLocal() as db:
        match_count = db.execute(
            text("SELECT COUNT(*) FROM matches WHERE id = ANY(:ids)"),
            {"ids": seeded_ids},
        ).scalar()
        pred_count = db.execute(
            text(
                "SELECT COUNT(*) FROM predictions "
                "WHERE model_version = 'test' AND match_id = ANY(:ids)"
            ),
            {"ids": seeded_ids},
        ).scalar()

    assert match_count == len(seeded_ids)
    assert pred_count == len(seeded_ids)

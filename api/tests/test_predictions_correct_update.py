"""Test that _insert_match_data backfills predictions.correct when a match
result is known.

The home page surfaces 'upcoming' matches as the ones whose prediction has
correct IS NULL. When the recent-results scraper later inserts the completed
match, we want predictions tied to that match to flip to True/False so the
match transitions to history automatically.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import SyncSessionLocal
from app.services.scraper import _insert_match_data


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


# Use IDs in a high range to avoid clashing with real production data.
MATCH_ID = 999_900_001
TEAM1_NAME = "__test_pred_correct_team1__"
TEAM2_NAME = "__test_pred_correct_team2__"


def _cleanup(db):
    db.execute(text("DELETE FROM predictions WHERE match_id = :mid"), {"mid": MATCH_ID})
    db.execute(text("DELETE FROM odds WHERE match_id = :mid"), {"mid": MATCH_ID})
    db.execute(
        text("DELETE FROM player_map_stats WHERE map_id IN "
             "(SELECT id FROM maps WHERE match_id = :mid)"),
        {"mid": MATCH_ID},
    )
    db.execute(
        text("DELETE FROM rounds WHERE map_id IN "
             "(SELECT id FROM maps WHERE match_id = :mid)"),
        {"mid": MATCH_ID},
    )
    db.execute(text("DELETE FROM map_vetos WHERE match_id = :mid"), {"mid": MATCH_ID})
    db.execute(text("DELETE FROM maps WHERE match_id = :mid"), {"mid": MATCH_ID})
    db.execute(text("DELETE FROM matches WHERE id = :mid"), {"mid": MATCH_ID})
    db.execute(
        text("DELETE FROM teams WHERE name IN (:n1, :n2)"),
        {"n1": TEAM1_NAME, "n2": TEAM2_NAME},
    )


@pytest.fixture
def seeded_match_with_prediction():
    """Seed two teams, an upcoming-match shell, and a NULL-correct prediction.

    Yields (team1_id, team2_id, prediction_id).
    """
    with SyncSessionLocal() as db:
        _cleanup(db)
        db.commit()

        team1_id = db.execute(
            text("INSERT INTO teams (name) VALUES (:n) RETURNING id"),
            {"n": TEAM1_NAME},
        ).scalar()
        team2_id = db.execute(
            text("INSERT INTO teams (name) VALUES (:n) RETURNING id"),
            {"n": TEAM2_NAME},
        ).scalar()

        # Upcoming-match shell: NULL scores + winner.
        db.execute(
            text("""
                INSERT INTO matches (id, team1_id, team2_id, team1_score, team2_score)
                VALUES (:mid, :t1, :t2, NULL, NULL)
            """),
            {"mid": MATCH_ID, "t1": team1_id, "t2": team2_id},
        )

        prediction_id = db.execute(
            text("""
                INSERT INTO predictions (
                    match_id, team1_id, team2_id, team1_win_prob,
                    predicted_at, model_version, correct
                ) VALUES (
                    :mid, :t1, :t2, 0.7, NOW(), 'test', NULL
                ) RETURNING id
            """),
            {"mid": MATCH_ID, "t1": team1_id, "t2": team2_id},
        ).scalar()

        db.commit()
        yield team1_id, team2_id, prediction_id

        _cleanup(db)
        db.commit()


def _completed_match(winner_team_name, t1_score, t2_score):
    return {
        "match_id": MATCH_ID,
        "team1": TEAM1_NAME,
        "team2": TEAM2_NAME,
        "team1_score": t1_score,
        "team2_score": t2_score,
        "winner": winner_team_name,
        "date": None,
        "time": None,
        "event": None,
        "stage": None,
        "match_url": None,
    }


def test_team1_win_marks_prediction_correct(seeded_match_with_prediction):
    team1_id, team2_id, prediction_id = seeded_match_with_prediction

    with SyncSessionLocal() as db:
        # Repopulate team_cache so _insert_match_data reuses existing IDs.
        team_cache = {TEAM1_NAME: team1_id, TEAM2_NAME: team2_id}
        match = _completed_match(TEAM1_NAME, 2, 1)
        _insert_match_data(db, match, [], [], team_cache, {})
        db.commit()

        correct = db.execute(
            text("SELECT correct FROM predictions WHERE id = :pid"),
            {"pid": prediction_id},
        ).scalar()

    # team1_win_prob = 0.7 (>= 0.5) and team1 won -> correct = True
    assert correct is True


def test_team2_win_marks_prediction_incorrect(seeded_match_with_prediction):
    team1_id, team2_id, prediction_id = seeded_match_with_prediction

    with SyncSessionLocal() as db:
        team_cache = {TEAM1_NAME: team1_id, TEAM2_NAME: team2_id}
        match = _completed_match(TEAM2_NAME, 0, 2)
        _insert_match_data(db, match, [], [], team_cache, {})
        db.commit()

        correct = db.execute(
            text("SELECT correct FROM predictions WHERE id = :pid"),
            {"pid": prediction_id},
        ).scalar()

    # team1_win_prob = 0.7 (>= 0.5) but team2 won -> correct = False
    assert correct is False

"""Compute Elo ratings for all teams and populate the team_elo table.

Usage:
    python -m app.services.compute_elo

Processes all maps chronologically (ordered by match date, then map_number)
and writes an Elo snapshot per team per map.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SyncSessionLocal, sync_engine
from app.models import TeamElo
from app.services.elo import EloEngine

logger = logging.getLogger(__name__)


def compute_all_elo(cancel_check: callable = None) -> None:
    """Walk through every map chronologically and compute Elo updates."""
    settings = get_settings()
    engine = EloEngine(
        k_factor=settings.elo_k_factor,
        start_elo=settings.elo_start,
        decay_days=settings.elo_decay_days,
        decay_rate=settings.elo_decay_rate,
    )

    session: Session = SyncSessionLocal()

    try:
        # Clear existing elo data
        session.execute(text("DELETE FROM team_elo"))
        session.flush()

        # Get all maps ordered by match date, then map_number
        # Join with matches to get date + team IDs, and maps for round scores
        rows = session.execute(
            text("""
                SELECT
                    m.id AS map_id,
                    m.match_id,
                    m.team1_score,
                    m.team2_score,
                    m.winner_id,
                    mt.team1_id,
                    mt.team2_id,
                    mt.date AS match_date
                FROM maps m
                JOIN matches mt ON m.match_id = mt.id
                WHERE mt.date IS NOT NULL
                  AND m.team1_score IS NOT NULL
                  AND m.team2_score IS NOT NULL
                ORDER BY mt.date ASC, m.match_id ASC, m.map_number ASC
            """)
        ).fetchall()

        logger.info("Processing %d maps...", len(rows))

        elo_records = []
        for i, row in enumerate(rows):
            map_id = row.map_id
            team1_id = row.team1_id
            team2_id = row.team2_id
            t1_score = row.team1_score
            t2_score = row.team2_score
            match_date = row.match_date

            if t1_score == t2_score:
                # Skip draws (shouldn't happen but be safe)
                continue

            u1, u2 = engine.update(team1_id, team2_id, t1_score, t2_score, match_date)

            elo_records.append(
                TeamElo(team_id=team1_id, map_id=map_id, elo=u1.new_elo, elo_delta=u1.delta)
            )
            elo_records.append(
                TeamElo(team_id=team2_id, map_id=map_id, elo=u2.new_elo, elo_delta=u2.delta)
            )

            # Batch insert every 2000 records
            if len(elo_records) >= 2000:
                session.add_all(elo_records)
                session.flush()
                elo_records.clear()

            if (i + 1) % 2000 == 0:
                logger.info("  %d/%d maps processed...", i + 1, len(rows))
                if cancel_check:
                    cancel_check()

        # Flush remaining
        if elo_records:
            session.add_all(elo_records)

        session.commit()
        logger.info("Done. Wrote %d Elo snapshots for %d teams.", len(rows) * 2, len(engine.ratings))

        # Log top 10 teams
        top_teams = sorted(engine.ratings.items(), key=lambda x: x[1], reverse=True)[:10]
        team_names = dict(
            session.execute(text("SELECT id, name FROM teams")).fetchall()
        )
        logger.info("Top 10 teams by final Elo:")
        for team_id, elo in top_teams:
            name = team_names.get(team_id, f"Team {team_id}")
            logger.info("  %7.1f  %s", elo, name)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    compute_all_elo()

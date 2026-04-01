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

    def _make_engine() -> EloEngine:
        return EloEngine(
            k_factor=settings.elo_k_factor,
            start_elo=settings.elo_start,
            decay_days=settings.elo_decay_days,
            decay_rate=settings.elo_decay_rate,
        )

    global_engine = _make_engine()
    map_engines: dict[str, EloEngine] = {}

    session: Session = SyncSessionLocal()

    try:
        session.execute(text("DELETE FROM team_elo"))
        session.flush()

        rows = session.execute(
            text("""
                SELECT
                    m.id AS map_id,
                    m.match_id,
                    m.map_name,
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
            map_name = row.map_name
            team1_id = row.team1_id
            team2_id = row.team2_id
            t1_score = row.team1_score
            t2_score = row.team2_score
            match_date = row.match_date

            if t1_score == t2_score:
                continue

            # Global Elo update
            u1, u2 = global_engine.update(team1_id, team2_id, t1_score, t2_score, match_date)

            elo_records.append(
                TeamElo(team_id=team1_id, map_id=map_id, elo=u1.new_elo, elo_delta=u1.delta, map_name=None)
            )
            elo_records.append(
                TeamElo(team_id=team2_id, map_id=map_id, elo=u2.new_elo, elo_delta=u2.delta, map_name=None)
            )

            # Per-map Elo update
            if map_name:
                if map_name not in map_engines:
                    map_engines[map_name] = _make_engine()
                mu1, mu2 = map_engines[map_name].update(team1_id, team2_id, t1_score, t2_score, match_date)

                elo_records.append(
                    TeamElo(team_id=team1_id, map_id=map_id, elo=mu1.new_elo, elo_delta=mu1.delta, map_name=map_name)
                )
                elo_records.append(
                    TeamElo(team_id=team2_id, map_id=map_id, elo=mu2.new_elo, elo_delta=mu2.delta, map_name=map_name)
                )

            if len(elo_records) >= 2000:
                session.add_all(elo_records)
                session.flush()
                elo_records.clear()

            if (i + 1) % 2000 == 0:
                logger.info("  %d/%d maps processed...", i + 1, len(rows))
                if cancel_check:
                    cancel_check()

        if elo_records:
            session.add_all(elo_records)

        session.commit()
        logger.info("Done. Wrote Elo snapshots for %d teams across %d maps.", len(global_engine.ratings), len(map_engines))

        top_teams = sorted(global_engine.ratings.items(), key=lambda x: x[1], reverse=True)[:10]
        team_names = dict(
            session.execute(text("SELECT id, name FROM teams")).fetchall()
        )
        logger.info("Top 10 teams by global Elo:")
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

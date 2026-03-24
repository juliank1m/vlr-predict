"""Import raw CSVs from vlr-scraper into PostgreSQL.

Usage:
    python -m app.services.import_csv --data-dir /path/to/vlr-scraper/data/raw

Expects three pipe-delimited CSVs:
    matches.csv, games.csv, player_stats.csv
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SyncSessionLocal, sync_engine
from app.models import Base, Map, Match, Player, PlayerMapStat, Team


def parse_date(date_str: str | None) -> datetime | None:
    """Parse VLR date strings like 'Fri, January 16, 2026'."""
    if not date_str or pd.isna(date_str):
        return None
    try:
        return pd.to_datetime(date_str).to_pydatetime()
    except Exception:
        return None


def to_int(val) -> int | None:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def to_float(val) -> float | None:
    if isinstance(val, str):
        val = val.replace("%", "").strip()
    try:
        result = float(val)
        return None if np.isnan(result) else result
    except (ValueError, TypeError):
        return None

def to_str(val) -> str | None:
    """Convert a value to a clean string, or None if empty/NaN."""
    if val is None:
        return None
    if isinstance(val, float):
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None


def get_or_create_team(session: Session, name, team_cache: dict[str, int]) -> int | None:
    """Return team ID, creating the team if it doesn't exist."""
    if not isinstance(name, str) or not name.strip():
        return None
    normalized = name.strip()
    if normalized in team_cache:
        return team_cache[normalized]

    team = Team(name=normalized)
    session.add(team)
    session.flush()
    team_cache[normalized] = team.id
    return team.id


def get_or_create_player(
    session: Session,
    player_id_raw,
    player_name: str,
    player_url: str | None,
    player_cache: dict[int, int],
) -> int | None:
    """Return player ID, creating the player if needed."""
    pid = to_int(player_id_raw)
    if pid is None:
        return None
    if pid in player_cache:
        return pid

    player = Player(id=pid, name=player_name.strip(), url=player_url)
    session.merge(player)
    session.flush()
    player_cache[pid] = pid
    return pid


def import_data(data_dir: Path) -> None:
    """Load all three CSVs into the database."""
    matches_path = data_dir / "matches.csv"
    games_path = data_dir / "games.csv"
    player_stats_path = data_dir / "player_stats.csv"

    for path in [matches_path, games_path, player_stats_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing: {path}")

    print("Reading CSVs...")
    matches_df = pd.read_csv(matches_path, sep="|", dtype=str)
    games_df = pd.read_csv(games_path, sep="|", dtype=str)
    players_df = pd.read_csv(player_stats_path, sep="|", dtype=str)

    print(f"  matches: {len(matches_df)} rows")
    print(f"  games:   {len(games_df)} rows")
    print(f"  players: {len(players_df)} rows")

    # Create tables
    Base.metadata.create_all(sync_engine)

    session = SyncSessionLocal()
    team_cache: dict[str, int] = {}
    player_cache: dict[int, int] = {}
    match_team_lookup: dict[int, tuple[int, int]] = {}  # match_id -> (team1_id, team2_id)

    try:
        # --- Import matches ---
        print("Importing matches...")
        for _, row in matches_df.iterrows():
            match_id = to_int(row.get("match_id"))
            team1_name = row.get("team1")
            team2_name = row.get("team2")
            winner_name = row.get("winner")

            if match_id is None or not team1_name or not team2_name:
                continue

            team1_id = get_or_create_team(session, team1_name, team_cache)
            team2_id = get_or_create_team(session, team2_name, team_cache)

            if team1_id is None or team2_id is None:
                continue

            match_team_lookup[match_id] = (team1_id, team2_id)

            winner_id = None
            if winner_name and isinstance(winner_name, str):
                winner_name = winner_name.strip()
                if winner_name == team1_name.strip():
                    winner_id = team1_id
                elif winner_name == team2_name.strip():
                    winner_id = team2_id

            match = Match(
                id=match_id,
                date=parse_date(row.get("date")),
                team1_id=team1_id,
                team2_id=team2_id,
                team1_score=to_int(row.get("team1_score")) or 0,
                team2_score=to_int(row.get("team2_score")) or 0,
                winner_id=winner_id,
                event=row.get("event"),
                stage=row.get("stage"),
                url=row.get("match_url"),
            )
            session.merge(match)

        session.flush()
        print(f"  {len(match_team_lookup)} matches imported")

        # --- Import maps/games ---
        print("Importing maps...")
        map_count = 0
        for _, row in games_df.iterrows():
            match_id = to_int(row.get("match_id"))
            game_id = to_int(row.get("game_id"))
            if match_id is None or game_id is None:
                continue
            if match_id not in match_team_lookup:
                continue

            team1_id, team2_id = match_team_lookup[match_id]

            t1_score = to_int(row.get("team1_score")) or 0
            t2_score = to_int(row.get("team2_score")) or 0

            winner_id = None
            if t1_score > t2_score:
                winner_id = team1_id
            elif t2_score > t1_score:
                winner_id = team2_id

            game_map = Map(
                id=game_id,
                match_id=match_id,
                map_number=to_int(row.get("map_number")) or 1,
                map_name=row.get("map_name"),
                team1_score=t1_score,
                team2_score=t2_score,
                winner_id=winner_id,
            )
            session.merge(game_map)
            map_count += 1

        session.flush()
        print(f"  {map_count} maps imported")

        # --- Import player stats ---
        print("Importing player stats...")
        stat_count = 0
        for _, row in players_df.iterrows():
            game_id = to_int(row.get("game_id"))
            if game_id is None:
                continue

            match_id = to_int(row.get("match_id"))
            if match_id is None or match_id not in match_team_lookup:
                continue

            player_name = row.get("player_name")
            if not player_name:
                continue

            player_id = get_or_create_player(
                session,
                row.get("player_id"),
                player_name,
                row.get("player_url"),
                player_cache,
            )
            if player_id is None:
                continue

            # Resolve team_id from team_name
            team_name = str(row.get("team_name", "")).strip()
            if team_name not in team_cache:
                team_id = get_or_create_team(session, team_name, team_cache)
            else:
                team_id = team_cache[team_name]

            stat = PlayerMapStat(
                map_id=game_id,
                player_id=player_id,
                team_id=team_id,
                agent=to_str(row.get("agent")),
                rating=to_float(row.get("rating")),
                acs=to_float(row.get("acs")),
                kills=to_int(row.get("kills")),
                deaths=to_int(row.get("deaths")),
                assists=to_int(row.get("assists")),
                kast=to_float(row.get("kast")),
                adr=to_float(row.get("adr")),
                hs_percent=to_float(row.get("hs_percent")),
                first_kills=to_int(row.get("first_kills")),
                first_deaths=to_int(row.get("first_deaths")),
            )
            session.add(stat)
            stat_count += 1

            # Batch flush every 5000 rows
            if stat_count % 5000 == 0:
                session.flush()
                print(f"    {stat_count} player stats...")

        session.commit()
        print(f"  {stat_count} player stats imported")
        print(f"\nDone. {len(team_cache)} teams, {len(player_cache)} players.")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Import VLR scraped CSVs into PostgreSQL.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Path to directory containing matches.csv, games.csv, player_stats.csv",
    )
    args = parser.parse_args()
    import_data(args.data_dir)


if __name__ == "__main__":
    main()

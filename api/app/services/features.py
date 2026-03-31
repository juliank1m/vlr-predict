"""Feature engineering pipeline for match prediction.

Computes all features for a given matchup using only data available
before the match starts (no future leakage).

Usage:
    from app.services.features import compute_features
    from app.database import SyncSessionLocal

    with SyncSessionLocal() as session:
        features = compute_features(
            session, team1_id=1, team2_id=2,
            map_name="Ascent", match_date=datetime(2024, 3, 15),
        )

For batch training, precompute global medians once:

    medians = compute_global_medians(session)
    for match in matches:
        features = compute_features(session, ..., global_medians=medians)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_MAPS_FOR_STATS = 3
_ROLLING_WINDOWS = (10, 20)
_STAT_KEYS = (
    "avg_rating", "avg_acs", "avg_kast", "avg_adr",
    "fk_rate", "fd_rate", "win_rate",
)

DEFAULT_MEDIANS: dict[str, float] = {
    "avg_rating": 1.0,
    "avg_acs": 200.0,
    "avg_kast": 70.0,
    "avg_adr": 140.0,
    "fk_rate": 3.0,
    "fd_rate": 3.0,
    "win_rate": 0.5,
}

# Build feature name list programmatically for consistency
FEATURE_NAMES: list[str] = ["team1_elo", "team2_elo", "elo_diff"]
for _n in _ROLLING_WINDOWS:
    for _side in ("team1", "team2"):
        FEATURE_NAMES += [f"{_side}_{k}_{_n}" for k in _STAT_KEYS]
    FEATURE_NAMES += [f"{k}_diff_{_n}" for k in _STAT_KEYS]
FEATURE_NAMES += [
    "team1_map_win_rate", "team2_map_win_rate",
    "team1_map_games_played", "team2_map_games_played",
    "map_win_rate_diff",
    "h2h_team1_win_rate", "h2h_maps_played",
    "team1_days_since_last", "team2_days_since_last",
    "team1_streak", "team2_streak",
    "team1_recent_momentum", "team2_recent_momentum",
    "team1_roster_overlap", "team2_roster_overlap",
]
FEATURE_NAMES += [
    "is_team1_pick", "is_team2_pick", "is_decider",
    "team1_pick_win_rate", "team2_pick_win_rate",
]

# ---------------------------------------------------------------------------
# SQL Templates (module-level for reuse across calls)
# ---------------------------------------------------------------------------

_ELO_SQL = text("""
    SELECT te.elo
    FROM team_elo te
    JOIN maps m ON te.map_id = m.id
    JOIN matches mt ON m.match_id = mt.id
    WHERE te.team_id = :team_id
      AND mt.date IS NOT NULL
      AND mt.date < :match_date
    ORDER BY mt.date DESC, m.map_number DESC
    LIMIT 1
""")

_ROLLING_SQL = text("""
    WITH recent_maps AS (
        SELECT m.id AS map_id, m.winner_id
        FROM maps m
        JOIN matches mt ON m.match_id = mt.id
        WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
          AND mt.date IS NOT NULL
          AND mt.date < :match_date
        ORDER BY mt.date DESC, m.map_number DESC
        LIMIT :n
    )
    SELECT
        AVG(ps.rating),
        AVG(ps.acs),
        AVG(ps.kast),
        AVG(ps.adr),
        CAST(SUM(ps.first_kills) AS float)
            / NULLIF((SELECT COUNT(*) FROM recent_maps), 0),
        CAST(SUM(ps.first_deaths) AS float)
            / NULLIF((SELECT COUNT(*) FROM recent_maps), 0),
        (SELECT COUNT(*) FROM recent_maps),
        (SELECT CAST(COUNT(*) FILTER (WHERE winner_id = :team_id) AS float)
              / NULLIF(COUNT(*), 0)
         FROM recent_maps)
    FROM player_map_stats ps
    WHERE ps.team_id = :team_id
      AND ps.map_id IN (SELECT map_id FROM recent_maps)
""")

_MAP_WIN_SQL = text("""
    WITH map_history AS (
        SELECT m.id AS map_id, m.winner_id
        FROM maps m
        JOIN matches mt ON m.match_id = mt.id
        WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
          AND m.map_name = :map_name
          AND mt.date IS NOT NULL
          AND mt.date < :match_date
        ORDER BY mt.date DESC, m.map_number DESC
        LIMIT 20
    )
    SELECT
        CAST(COUNT(*) FILTER (WHERE winner_id = :team_id) AS float)
            / NULLIF(COUNT(*), 0),
        COUNT(*)
    FROM map_history
""")

_H2H_SQL = text("""
    SELECT
        CAST(COUNT(*) FILTER (WHERE m.winner_id = :team1_id) AS float)
            / NULLIF(COUNT(*), 0),
        COUNT(*)
    FROM maps m
    JOIN matches mt ON m.match_id = mt.id
    WHERE mt.date IS NOT NULL
      AND mt.date < :match_date
      AND (
          (mt.team1_id = :team1_id AND mt.team2_id = :team2_id)
          OR (mt.team1_id = :team2_id AND mt.team2_id = :team1_id)
      )
""")

_RECENCY_SQL = text("""
    SELECT mt.date, m.winner_id
    FROM maps m
    JOIN matches mt ON m.match_id = mt.id
    WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
      AND mt.date IS NOT NULL
      AND mt.date < :match_date
      AND m.winner_id IS NOT NULL
    ORDER BY mt.date DESC, m.map_number DESC
    LIMIT 20
""")

_ROSTER_SQL = text("""
    WITH most_recent AS (
        SELECT m.id AS map_id
        FROM maps m
        JOIN matches mt ON m.match_id = mt.id
        WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
          AND mt.date IS NOT NULL
          AND mt.date < :match_date
        ORDER BY mt.date DESC, m.map_number DESC
        LIMIT 1
    ),
    current_roster AS (
        SELECT player_id
        FROM player_map_stats
        WHERE map_id = (SELECT map_id FROM most_recent)
          AND team_id = :team_id
    ),
    prev_maps AS (
        SELECT m.id AS map_id
        FROM maps m
        JOIN matches mt ON m.match_id = mt.id
        WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
          AND mt.date IS NOT NULL
          AND mt.date < :match_date
          AND m.id != COALESCE((SELECT map_id FROM most_recent), -1)
        ORDER BY mt.date DESC, m.map_number DESC
        LIMIT 10
    ),
    roster_overlaps AS (
        SELECT ps.map_id, COUNT(DISTINCT ps.player_id) AS overlap_count
        FROM player_map_stats ps
        WHERE ps.team_id = :team_id
          AND ps.map_id IN (SELECT map_id FROM prev_maps)
          AND ps.player_id IN (SELECT player_id FROM current_roster)
        GROUP BY ps.map_id
    )
    SELECT
        (SELECT COUNT(*) FROM current_roster),
        (SELECT COUNT(*) FROM prev_maps),
        (SELECT COALESCE(SUM(overlap_count), 0) FROM roster_overlaps)
""")


_PICK_WIN_RATE_SQL = text("""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN m.winner_id = m.picked_by THEN 1 ELSE 0 END) AS wins
    FROM maps m
    JOIN matches mt ON m.match_id = mt.id
    WHERE m.picked_by = :team_id
      AND mt.date IS NOT NULL
      AND mt.date < :match_date
""")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_features(
    session: Session,
    team1_id: int,
    team2_id: int,
    map_name: str | None,
    match_date: datetime,
    *,
    map_id: int | None = None,
    global_medians: dict[str, float] | None = None,
) -> dict[str, float | None]:
    """Compute all features for a team1 vs team2 matchup.

    All rolling stats use only maps where match.date < match_date.

    Args:
        session: SQLAlchemy sync session.
        team1_id: ID of team 1.
        team2_id: ID of team 2.
        map_name: Specific map (e.g. "Ascent"), or None for unknown.
        match_date: Cutoff — only data before this is used.
        global_medians: Precomputed medians for cold-start imputation.
            Use compute_global_medians() for batch jobs.

    Returns:
        Dict of feature name -> value. None for unavailable features.
    """
    medians = global_medians or DEFAULT_MEDIANS
    f: dict[str, float | None] = {}

    f.update(_elo_features(session, team1_id, team2_id, match_date))

    for n in _ROLLING_WINDOWS:
        f.update(_rolling_features(session, team1_id, team2_id, match_date, n, medians))

    f.update(_map_features(session, team1_id, team2_id, map_name, match_date, f))
    f.update(_h2h_features(session, team1_id, team2_id, match_date))
    f.update(_recency_features(session, team1_id, team2_id, match_date))
    f.update(_roster_features(session, team1_id, team2_id, match_date))
    f.update(_pick_ban_features(session, team1_id, team2_id, map_id, match_date))

    return f


def compute_global_medians(session: Session) -> dict[str, float]:
    """Compute global median stats for cold-start imputation.

    Call once before batch feature computation and pass as global_medians
    to compute_features() to avoid redundant work.
    """
    row = session.execute(text("""
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rating),
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY acs),
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY kast),
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY adr)
        FROM player_map_stats
        WHERE rating IS NOT NULL
    """)).fetchone()

    fk_row = session.execute(text("""
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fk_per_map),
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fd_per_map)
        FROM (
            SELECT map_id, team_id,
                   SUM(first_kills) AS fk_per_map,
                   SUM(first_deaths) AS fd_per_map
            FROM player_map_stats
            WHERE first_kills IS NOT NULL
            GROUP BY map_id, team_id
        ) sub
    """)).fetchone()

    return {
        "avg_rating": float(row[0]) if row and row[0] else 1.0,
        "avg_acs": float(row[1]) if row and row[1] else 200.0,
        "avg_kast": float(row[2]) if row and row[2] else 70.0,
        "avg_adr": float(row[3]) if row and row[3] else 140.0,
        "fk_rate": float(fk_row[0]) if fk_row and fk_row[0] else 3.0,
        "fd_rate": float(fk_row[1]) if fk_row and fk_row[1] else 3.0,
        "win_rate": 0.5,
    }


def feature_vector(features: dict[str, float | None]) -> list[float | None]:
    """Convert feature dict to ordered list matching FEATURE_NAMES."""
    return [features.get(name) for name in FEATURE_NAMES]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_float(val: object) -> float | None:
    return float(val) if val is not None else None


def _elo_features(
    session: Session, team1_id: int, team2_id: int, match_date: datetime,
) -> dict[str, float]:
    f: dict[str, float] = {}
    for label, tid in (("team1", team1_id), ("team2", team2_id)):
        row = session.execute(
            _ELO_SQL, {"team_id": tid, "match_date": match_date},
        ).fetchone()
        f[f"{label}_elo"] = float(row[0]) if row else 1500.0
    f["elo_diff"] = f["team1_elo"] - f["team2_elo"]
    return f


def _team_rolling(
    session: Session, team_id: int, match_date: datetime, n: int,
    medians: dict[str, float],
) -> dict[str, float | None]:
    """Rolling stats for one team over their last n maps."""
    row = session.execute(
        _ROLLING_SQL, {"team_id": team_id, "match_date": match_date, "n": n},
    ).fetchone()

    num_maps = int(row[6]) if row and row[6] else 0

    if num_maps < MIN_MAPS_FOR_STATS:
        return {k: medians.get(k) for k in _STAT_KEYS}

    stats: dict[str, float | None] = {
        "avg_rating": _to_float(row[0]),
        "avg_acs": _to_float(row[1]),
        "avg_kast": _to_float(row[2]),
        "avg_adr": _to_float(row[3]),
        "fk_rate": _to_float(row[4]),
        "fd_rate": _to_float(row[5]),
        "win_rate": _to_float(row[7]),
    }
    for k in _STAT_KEYS:
        if stats[k] is None:
            stats[k] = medians.get(k)
    return stats


def _rolling_features(
    session: Session, team1_id: int, team2_id: int,
    match_date: datetime, n: int, medians: dict[str, float],
) -> dict[str, float | None]:
    f: dict[str, float | None] = {}
    for label, tid in (("team1", team1_id), ("team2", team2_id)):
        stats = _team_rolling(session, tid, match_date, n, medians)
        for k in _STAT_KEYS:
            f[f"{label}_{k}_{n}"] = stats[k]

    for k in _STAT_KEYS:
        t1 = f.get(f"team1_{k}_{n}")
        t2 = f.get(f"team2_{k}_{n}")
        f[f"{k}_diff_{n}"] = (t1 - t2) if (t1 is not None and t2 is not None) else None

    return f


def _map_features(
    session: Session, team1_id: int, team2_id: int,
    map_name: str | None, match_date: datetime,
    existing: dict[str, float | None],
) -> dict[str, float | None]:
    f: dict[str, float | None] = {}

    if map_name is None:
        for k in ("team1_map_win_rate", "team2_map_win_rate",
                   "team1_map_games_played", "team2_map_games_played",
                   "map_win_rate_diff"):
            f[k] = None
        return f

    for label, tid in (("team1", team1_id), ("team2", team2_id)):
        row = session.execute(
            _MAP_WIN_SQL,
            {"team_id": tid, "map_name": map_name, "match_date": match_date},
        ).fetchone()

        games = int(row[1]) if row and row[1] else 0

        if games < MIN_MAPS_FOR_STATS:
            f[f"{label}_map_win_rate"] = existing.get(f"{label}_win_rate_20")
        else:
            f[f"{label}_map_win_rate"] = _to_float(row[0])

        f[f"{label}_map_games_played"] = float(games)

    t1 = f.get("team1_map_win_rate")
    t2 = f.get("team2_map_win_rate")
    f["map_win_rate_diff"] = (t1 - t2) if (t1 is not None and t2 is not None) else None
    return f


def _h2h_features(
    session: Session, team1_id: int, team2_id: int, match_date: datetime,
) -> dict[str, float | None]:
    row = session.execute(
        _H2H_SQL,
        {"team1_id": team1_id, "team2_id": team2_id, "match_date": match_date},
    ).fetchone()

    maps_played = int(row[1]) if row and row[1] else 0
    return {
        "h2h_team1_win_rate": _to_float(row[0]) if maps_played > 0 else None,
        "h2h_maps_played": float(maps_played),
    }


def _team_recency(
    session: Session, team_id: int, match_date: datetime,
) -> dict[str, float | None]:
    rows = session.execute(
        _RECENCY_SQL, {"team_id": team_id, "match_date": match_date},
    ).fetchall()

    if not rows:
        return {"days_since_last": None, "streak": 0.0, "recent_momentum": None}

    # Days since last map
    last_date = rows[0][0]
    days = float((match_date - last_date).days) if last_date else None

    # Streak: consecutive wins or losses from most recent, capped at ±5
    streak = 0
    first_won = rows[0][1] == team_id
    for r in rows:
        if (r[1] == team_id) == first_won:
            streak += 1
        else:
            break
    streak = min(streak, 5) if first_won else max(-streak, -5)

    # Momentum: win rate in last 5 maps minus win rate in last 20
    n5 = min(len(rows), 5)
    wr5 = sum(1 for r in rows[:n5] if r[1] == team_id) / n5
    wr20 = sum(1 for r in rows if r[1] == team_id) / len(rows)

    return {
        "days_since_last": days,
        "streak": float(streak),
        "recent_momentum": wr5 - wr20,
    }


def _recency_features(
    session: Session, team1_id: int, team2_id: int, match_date: datetime,
) -> dict[str, float | None]:
    f: dict[str, float | None] = {}
    for label, tid in (("team1", team1_id), ("team2", team2_id)):
        rec = _team_recency(session, tid, match_date)
        f[f"{label}_days_since_last"] = rec["days_since_last"]
        f[f"{label}_streak"] = rec["streak"]
        f[f"{label}_recent_momentum"] = rec["recent_momentum"]
    return f


def _roster_features(
    session: Session, team1_id: int, team2_id: int, match_date: datetime,
) -> dict[str, float | None]:
    f: dict[str, float | None] = {}
    for label, tid in (("team1", team1_id), ("team2", team2_id)):
        row = session.execute(
            _ROSTER_SQL, {"team_id": tid, "match_date": match_date},
        ).fetchone()

        roster_size = int(row[0]) if row and row[0] else 0
        num_prev = int(row[1]) if row and row[1] else 0
        total_overlap = int(row[2]) if row and row[2] else 0

        if roster_size > 0 and num_prev > 0:
            f[f"{label}_roster_overlap"] = total_overlap / (roster_size * num_prev)
        else:
            f[f"{label}_roster_overlap"] = None
    return f


def _pick_ban_features(
    session: Session, team1_id: int, team2_id: int,
    map_id: int | None, match_date: datetime,
) -> dict[str, float | None]:
    """Compute pick/ban features for a map."""
    f: dict[str, float | None] = {
        "is_team1_pick": 0.0,
        "is_team2_pick": 0.0,
        "is_decider": 1.0,  # default to decider if no pick info
        "team1_pick_win_rate": None,
        "team2_pick_win_rate": None,
    }

    # Check who picked this map
    if map_id:
        row = session.execute(
            text("SELECT picked_by FROM maps WHERE id = :map_id"),
            {"map_id": map_id},
        ).fetchone()
        if row and row[0]:
            picked_by = row[0]
            if picked_by == team1_id:
                f["is_team1_pick"] = 1.0
                f["is_team2_pick"] = 0.0
                f["is_decider"] = 0.0
            elif picked_by == team2_id:
                f["is_team1_pick"] = 0.0
                f["is_team2_pick"] = 1.0
                f["is_decider"] = 0.0

    # Historical pick win rates
    for label, tid in (("team1", team1_id), ("team2", team2_id)):
        row = session.execute(
            _PICK_WIN_RATE_SQL, {"team_id": tid, "match_date": match_date},
        ).fetchone()
        if row and row.total and row.total >= 3:
            f[f"{label}_pick_win_rate"] = float(row.wins) / float(row.total)

    return f

"""Team endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from app.database import SyncSessionLocal

router = APIRouter()


def _list_teams_sync(search: str | None, limit: int) -> dict[str, object]:
    pattern = f"%{search}%" if search else None
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    t.id,
                    t.name,
                    t.first_seen,
                    (
                        SELECT te.elo
                        FROM team_elo te
                        JOIN maps m ON m.id = te.map_id
                        JOIN matches mt ON mt.id = m.match_id
                        WHERE te.team_id = t.id
                          AND mt.date IS NOT NULL
                        ORDER BY mt.date DESC, m.map_number DESC
                        LIMIT 1
                    ) AS current_elo
                FROM teams t
                WHERE (:pattern IS NULL OR t.name ILIKE :pattern)
                ORDER BY t.name
                LIMIT :limit
                """
            ),
            {"pattern": pattern, "limit": limit},
        ).mappings().all()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


def _get_team_sync(team_id: int) -> dict[str, object] | None:
    with SyncSessionLocal() as session:
        team_row = session.execute(
            text(
                """
                SELECT
                    t.id,
                    t.name,
                    t.first_seen,
                    (
                        SELECT te.elo
                        FROM team_elo te
                        JOIN maps m ON m.id = te.map_id
                        JOIN matches mt ON mt.id = m.match_id
                        WHERE te.team_id = t.id
                          AND mt.date IS NOT NULL
                        ORDER BY mt.date DESC, m.map_number DESC
                        LIMIT 1
                    ) AS current_elo
                FROM teams t
                WHERE t.id = :team_id
                """
            ),
            {"team_id": team_id},
        ).mappings().first()
        if team_row is None:
            return None

        elo_history = session.execute(
            text(
                """
                SELECT mt.date, m.id AS map_id, m.map_name, te.elo, te.elo_delta
                FROM team_elo te
                JOIN maps m ON m.id = te.map_id
                JOIN matches mt ON mt.id = m.match_id
                WHERE te.team_id = :team_id
                  AND mt.date IS NOT NULL
                ORDER BY mt.date, m.map_number, m.id
                """
            ),
            {"team_id": team_id},
        ).mappings().all()

        recent_matches = session.execute(
            text(
                """
                SELECT
                    mt.id AS match_id,
                    mt.date,
                    CASE
                        WHEN mt.team1_id = :team_id THEN mt.team2_id
                        ELSE mt.team1_id
                    END AS opponent_id,
                    CASE
                        WHEN mt.team1_id = :team_id THEN t2.name
                        ELSE t1.name
                    END AS opponent_name,
                    mt.team1_score,
                    mt.team2_score,
                    mt.winner_id,
                    mt.event,
                    mt.stage
                FROM matches mt
                JOIN teams t1 ON t1.id = mt.team1_id
                JOIN teams t2 ON t2.id = mt.team2_id
                WHERE mt.team1_id = :team_id OR mt.team2_id = :team_id
                ORDER BY mt.date DESC NULLS LAST, mt.id DESC
                LIMIT 10
                """
            ),
            {"team_id": team_id},
        ).mappings().all()

        map_pool = session.execute(
            text(
                """
                SELECT
                    m.map_name,
                    COUNT(*) AS maps_played,
                    AVG(CASE WHEN m.winner_id = :team_id THEN 1.0 ELSE 0.0 END) AS win_rate
                FROM maps m
                JOIN matches mt ON mt.id = m.match_id
                WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
                  AND mt.date IS NOT NULL
                  AND m.map_name IS NOT NULL
                  AND m.winner_id IS NOT NULL
                GROUP BY m.map_name
                ORDER BY maps_played DESC, m.map_name
                """
            ),
            {"team_id": team_id},
        ).mappings().all()

    return {
        **dict(team_row),
        "elo_history": [dict(row) for row in elo_history],
        "recent_matches": [dict(row) for row in recent_matches],
        "map_pool": [dict(row) for row in map_pool],
    }


def _get_team_players_sync(team_id: int) -> list[dict[str, object]]:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                WITH last_map AS (
                    SELECT m.id AS map_id
                    FROM maps m
                    JOIN matches mt ON mt.id = m.match_id
                    WHERE (mt.team1_id = :team_id OR mt.team2_id = :team_id)
                      AND mt.date IS NOT NULL
                    ORDER BY mt.date DESC, m.map_number DESC, m.id DESC
                    LIMIT 1
                )
                SELECT
                    p.id,
                    p.name,
                    p.url,
                    COUNT(*) AS appearances,
                    MAX(mt.date) AS last_played,
                    AVG(ps.rating) AS avg_rating,
                    MAX(
                        CASE
                            WHEN ps.map_id = (SELECT map_id FROM last_map) THEN 1
                            ELSE 0
                        END
                    ) = 1 AS is_current
                FROM player_map_stats ps
                JOIN players p ON p.id = ps.player_id
                JOIN maps m ON m.id = ps.map_id
                JOIN matches mt ON mt.id = m.match_id
                WHERE ps.team_id = :team_id
                GROUP BY p.id, p.name, p.url
                ORDER BY is_current DESC, last_played DESC NULLS LAST, appearances DESC
                """
            ),
            {"team_id": team_id},
        ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/")
async def list_teams(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List all teams."""
    return await run_in_threadpool(_list_teams_sync, search, limit)


@router.get("/{team_id}")
async def get_team(team_id: int):
    """Get team profile with Elo history and recent form."""
    result = await run_in_threadpool(_get_team_sync, team_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    return result


@router.get("/{team_id}/players")
async def get_team_players(team_id: int):
    """Get current and historical roster information for a team."""
    team = await run_in_threadpool(_get_team_sync, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    players = await run_in_threadpool(_get_team_players_sync, team_id)
    return {
        "team_id": team_id,
        "team_name": team["name"],
        "players": players,
    }

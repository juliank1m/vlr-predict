"""Match endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text

from app.database import SyncSessionLocal

router = APIRouter()


def _list_matches_sync(page: int, page_size: int, resolved_only: bool) -> dict[str, object]:
    offset = (page - 1) * page_size
    with SyncSessionLocal() as session:
        total = session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM matches
                WHERE (:resolved_only = FALSE OR winner_id IS NOT NULL)
                """
            ),
            {"resolved_only": resolved_only},
        ).scalar()
        rows = session.execute(
            text(
                """
                SELECT
                    mt.id,
                    mt.date,
                    mt.team1_id,
                    t1.name AS team1_name,
                    mt.team2_id,
                    t2.name AS team2_name,
                    mt.team1_score,
                    mt.team2_score,
                    mt.winner_id,
                    w.name AS winner_name,
                    mt.event,
                    mt.stage,
                    mt.url,
                    COUNT(m.id) AS map_count
                FROM matches mt
                JOIN teams t1 ON t1.id = mt.team1_id
                JOIN teams t2 ON t2.id = mt.team2_id
                LEFT JOIN teams w ON w.id = mt.winner_id
                LEFT JOIN maps m ON m.match_id = mt.id
                WHERE (:resolved_only = FALSE OR mt.winner_id IS NOT NULL)
                GROUP BY
                    mt.id, mt.date, mt.team1_id, t1.name, mt.team2_id, t2.name,
                    mt.team1_score, mt.team2_score, mt.winner_id, w.name,
                    mt.event, mt.stage, mt.url
                ORDER BY mt.date DESC NULLS LAST, mt.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "resolved_only": resolved_only,
                "limit": page_size,
                "offset": offset,
            },
        ).mappings().all()

    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
    }


def _get_match_sync(match_id: int) -> dict[str, object] | None:
    with SyncSessionLocal() as session:
        match_row = session.execute(
            text(
                """
                SELECT
                    mt.id,
                    mt.date,
                    mt.team1_id,
                    t1.name AS team1_name,
                    mt.team2_id,
                    t2.name AS team2_name,
                    mt.team1_score,
                    mt.team2_score,
                    mt.winner_id,
                    w.name AS winner_name,
                    mt.event,
                    mt.stage,
                    mt.url
                FROM matches mt
                JOIN teams t1 ON t1.id = mt.team1_id
                JOIN teams t2 ON t2.id = mt.team2_id
                LEFT JOIN teams w ON w.id = mt.winner_id
                WHERE mt.id = :match_id
                """
            ),
            {"match_id": match_id},
        ).mappings().first()
        if match_row is None:
            return None

        maps = session.execute(
            text(
                """
                SELECT id, map_number, map_name, team1_score, team2_score, winner_id
                FROM maps
                WHERE match_id = :match_id
                ORDER BY map_number, id
                """
            ),
            {"match_id": match_id},
        ).mappings().all()

        map_payloads: list[dict[str, object]] = []
        for map_row in maps:
            stats = session.execute(
                text(
                    """
                    SELECT
                        ps.team_id,
                        p.id AS player_id,
                        p.name AS player_name,
                        ps.agent,
                        ps.rating,
                        ps.acs,
                        ps.kills,
                        ps.deaths,
                        ps.assists,
                        ps.kast,
                        ps.adr,
                        ps.hs_percent,
                        ps.first_kills,
                        ps.first_deaths
                    FROM player_map_stats ps
                    JOIN players p ON p.id = ps.player_id
                    WHERE ps.map_id = :map_id
                    ORDER BY ps.team_id, ps.rating DESC NULLS LAST, p.name
                    """
                ),
                {"map_id": map_row["id"]},
            ).mappings().all()
            payload = dict(map_row)
            payload["player_stats"] = [dict(row) for row in stats]
            map_payloads.append(payload)

        pred_rows = session.execute(
            text(
                """
                SELECT team1_id, team2_id, team1_win_prob, map_name, model_version, correct
                FROM predictions
                WHERE match_id = :match_id
                ORDER BY map_name NULLS FIRST
                """
            ),
            {"match_id": match_id},
        ).mappings().all()

    result = dict(match_row)
    result["maps"] = map_payloads
    result["predictions"] = [dict(row) for row in pred_rows]
    return result


@router.get("/")
async def list_matches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    resolved_only: bool = True,
):
    """List recent match results."""
    return await run_in_threadpool(_list_matches_sync, page, page_size, resolved_only)


@router.get("/{match_id}")
async def get_match(match_id: int):
    """Get match detail with map scores and stats."""
    result = await run_in_threadpool(_get_match_sync, match_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    return result

"""Scrape recent VLR match results, games, and player stats into the database.

Reuses parsing logic from the standalone scrape_vlr scripts but writes
directly to PostgreSQL via SQLAlchemy instead of CSVs.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SyncSessionLocal
from app.models import Map, Match, Player, PlayerMapStat, Team

logger = logging.getLogger(__name__)

BASE_URL = "https://www.vlr.gg"
RESULTS_URL = f"{BASE_URL}/matches/results"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_FETCH_ATTEMPTS = 4
RETRY_BASE_DELAY = 2


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch(session: requests.Session, url: str) -> BeautifulSoup:
    """Fetch a page with retries and return parsed HTML."""
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException:
            if attempt == MAX_FETCH_ATTEMPTS:
                raise
            delay = RETRY_BASE_DELAY * attempt
            logger.warning("Fetch %s failed (attempt %d), retrying in %ds", url, attempt, delay)
            time.sleep(delay)
    raise RuntimeError(f"Unable to fetch {url}")


def _get_text(tag: Tag | None) -> str | None:
    if not tag:
        return None
    t = tag.get_text(" ", strip=True)
    return t or None


def _get_direct_text(tag: Tag | None) -> str | None:
    if not tag:
        return None
    t = "".join(s.strip() for s in tag.find_all(string=True, recursive=False) if s.strip())
    return t or None


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _to_int(val) -> int | None:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _to_float(val) -> float | None:
    if isinstance(val, str):
        val = val.replace("%", "").strip()
    try:
        result = float(val)
        return None if result != result else result  # NaN check
    except (ValueError, TypeError):
        return None


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str or str(date_str).strip().lower() == "nan":
        return None
    try:
        return pd.to_datetime(date_str).to_pydatetime()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Results page parsing (adapted from scrape_results.py)
# ---------------------------------------------------------------------------

def _parse_results_page(soup: BeautifulSoup) -> list[dict]:
    """Parse a VLR results page into match dicts."""
    container = soup.select_one("div.col.mod-1")
    if not container:
        return []

    matches: list[dict] = []
    current_date: str | None = None

    for el in container.children:
        if not isinstance(el, Tag):
            continue
        classes = set(el.get("class", []))
        if "wf-label" in classes:
            current_date = _get_direct_text(el)
            continue
        if "wf-card" not in classes:
            continue
        for item in el.select("a.wf-module-item.match-item[href]"):
            href = item.get("href")
            status = _get_text(item.select_one(".ml-status"))
            if not href or status != "Completed":
                continue
            mid = re.search(r"/(\d+)/", href)
            if not mid:
                continue
            teams = [_get_text(t) for t in item.select(".match-item-vs-team-name .text-of")]
            scores = [_get_text(t) for t in item.select(".match-item-vs-team-score")]
            if len(teams) < 2 or len(scores) < 2:
                continue
            matches.append({
                "match_id": int(mid.group(1)),
                "match_url": f"{BASE_URL}{href}",
                "date": current_date,
                "team1": teams[0],
                "team2": teams[1],
                "team1_score": _to_int(scores[0]) or 0,
                "team2_score": _to_int(scores[1]) or 0,
                "winner": _get_text(item.select_one(".match-item-vs-team.mod-winner .text-of")),
                "event": _get_direct_text(item.select_one(".match-item-event")),
                "stage": _get_text(item.select_one(".match-item-event-series")),
            })
    return matches


# ---------------------------------------------------------------------------
# Match detail parsing (adapted from scrape_games.py + scrape_player_stats.py)
# ---------------------------------------------------------------------------

def _extract_games(soup: BeautifulSoup, match: dict) -> list[dict]:
    """Extract game/map rows from a match detail page."""
    # Build map number lookup from nav
    nav_lookup: dict[str, int] = {}
    for nav in soup.select(".vm-stats-gamesnav-item[data-game-id]"):
        gid = nav.get("data-game-id")
        if not gid or gid == "all":
            continue
        label = " ".join(nav.stripped_strings)
        mn = re.search(r"\b(\d+)\b", label)
        if mn:
            nav_lookup[gid] = int(mn.group(1))

    games: list[dict] = []
    for idx, panel in enumerate(soup.select(".vm-stats-game[data-game-id]"), start=1):
        gid = panel.get("data-game-id")
        if not gid or gid == "all":
            continue
        header = panel.find(class_="vm-stats-game-header")
        if not header:
            continue
        scores = [s.get_text(strip=True) for s in header.select(".score")]
        if len(scores) < 2:
            continue
        t1 = _to_int(re.search(r"-?\d+", scores[0]).group()) if re.search(r"-?\d+", scores[0]) else 0
        t2 = _to_int(re.search(r"-?\d+", scores[-1]).group()) if re.search(r"-?\d+", scores[-1]) else 0
        map_container = header.find(class_="map")
        map_name = None
        if map_container:
            mn_tag = map_container.find(string=re.compile(r"\S"))
            map_name = mn_tag.strip() if mn_tag else None

        games.append({
            "game_id": int(gid),
            "match_id": match["match_id"],
            "map_number": nav_lookup.get(gid, idx),
            "map_name": map_name,
            "team1_score": t1 or 0,
            "team2_score": t2 or 0,
        })
    return games


STAT_FIELDS = [
    "rating", "acs", "kills", "deaths", "assists",
    "kill_death_diff", "kast", "adr", "hs_percent",
    "first_kills", "first_deaths", "first_kill_death_diff",
]


def _extract_stat_value(cell: Tag) -> str | None:
    for sel in (".side.mod-side.mod-both", ".side.mod-both", ".mod-both"):
        side = cell.select_one(sel)
        if side:
            v = _normalize(side.get_text(" ", strip=True))
            if v:
                return v
    return _normalize(cell.get_text(" ", strip=True))


def _extract_players(soup: BeautifulSoup, match: dict, games: list[dict]) -> list[dict]:
    """Extract player stat rows from a match detail page."""
    panel_lookup: dict[str, Tag] = {}
    for panel in soup.select(".vm-stats-game[data-game-id]"):
        gid = panel.get("data-game-id")
        if gid and gid != "all":
            panel_lookup[gid] = panel

    rows: list[dict] = []
    for game in games:
        panel = panel_lookup.get(str(game["game_id"]))
        if not panel:
            continue

        # Get team names from header
        header = panel.find(class_="vm-stats-game-header")
        team_names = [match.get("team1"), match.get("team2")]
        if header:
            tn = [_normalize(t.get_text(" ", strip=True)) for t in header.select(".team-name")]
            if len(tn) >= 2:
                team_names = tn[:2]

        tables = panel.select("table.wf-table-inset.mod-overview")
        for ti, table in enumerate(tables[:2]):
            team_name = team_names[ti] if ti < len(team_names) else None
            for tr in table.select("tbody tr"):
                player_cell = tr.select_one("td.mod-player")
                if not player_cell:
                    continue
                link = player_cell.select_one("a[href*='/player/']")
                name_tag = player_cell.select_one(".text-of")
                pname = _normalize(name_tag.get_text(" ", strip=True) if name_tag else None)
                if not pname and link:
                    pname = _normalize(link.get_text(" ", strip=True))
                if not pname:
                    continue

                pid = None
                if link:
                    pid_match = re.search(r"/player/(\d+)/", link.get("href", ""))
                    pid = int(pid_match.group(1)) if pid_match else None

                stat_cells = tr.select("td.mod-stat")
                stats: dict[str, str | None] = {}
                for field, cell in zip(STAT_FIELDS, stat_cells):
                    stats[field] = _extract_stat_value(cell)

                # Agent
                agent_names = []
                for img in tr.select("td.mod-agents img"):
                    an = _normalize(img.get("title") or img.get("alt"))
                    if an and an not in agent_names:
                        agent_names.append(an)

                rows.append({
                    "game_id": game["game_id"],
                    "match_id": game["match_id"],
                    "team_name": team_name,
                    "player_id": pid,
                    "player_name": pname,
                    "agent": ", ".join(agent_names) if agent_names else None,
                    **stats,
                })
    return rows


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------

def _get_or_create_team(session: Session, name: str | None, cache: dict[str, int]) -> int | None:
    if not name or not name.strip():
        return None
    normalized = name.strip()
    if normalized in cache:
        return cache[normalized]
    team = Team(name=normalized)
    session.add(team)
    session.flush()
    cache[normalized] = team.id
    return team.id


def _get_or_create_player(session: Session, pid: int | None, name: str, cache: dict[int, bool]) -> int | None:
    if pid is None:
        return None
    if pid not in cache:
        session.merge(Player(id=pid, name=name.strip()))
        session.flush()
        cache[pid] = True
    return pid


def _insert_match_data(
    session: Session,
    match: dict,
    games: list[dict],
    players: list[dict],
    team_cache: dict[str, int],
    player_cache: dict[int, bool],
) -> None:
    """Insert a single match + its games + player stats into the DB."""
    t1_id = _get_or_create_team(session, match["team1"], team_cache)
    t2_id = _get_or_create_team(session, match["team2"], team_cache)
    if not t1_id or not t2_id:
        return

    winner_id = None
    w = match.get("winner")
    if w:
        w = w.strip()
        if w == match["team1"].strip():
            winner_id = t1_id
        elif w == match["team2"].strip():
            winner_id = t2_id

    session.merge(Match(
        id=match["match_id"],
        date=_parse_date(match.get("date")),
        team1_id=t1_id,
        team2_id=t2_id,
        team1_score=match["team1_score"],
        team2_score=match["team2_score"],
        winner_id=winner_id,
        event=match.get("event"),
        stage=match.get("stage"),
        url=match.get("match_url"),
    ))

    for g in games:
        g_t1 = g["team1_score"]
        g_t2 = g["team2_score"]
        g_winner = None
        if g_t1 > g_t2:
            g_winner = t1_id
        elif g_t2 > g_t1:
            g_winner = t2_id

        session.merge(Map(
            id=g["game_id"],
            match_id=g["match_id"],
            map_number=g["map_number"],
            map_name=g["map_name"],
            team1_score=g_t1,
            team2_score=g_t2,
            winner_id=g_winner,
        ))

    for p in players:
        team_id = _get_or_create_team(session, p.get("team_name"), team_cache)
        pid = _get_or_create_player(session, p.get("player_id"), p["player_name"], player_cache)

        session.add(PlayerMapStat(
            map_id=p["game_id"],
            player_id=pid,
            team_id=team_id,
            agent=p.get("agent"),
            rating=_to_float(p.get("rating")),
            acs=_to_float(p.get("acs")),
            kills=_to_int(p.get("kills")),
            deaths=_to_int(p.get("deaths")),
            assists=_to_int(p.get("assists")),
            kast=_to_float(p.get("kast")),
            adr=_to_float(p.get("adr")),
            hs_percent=_to_float(p.get("hs_percent")),
            first_kills=_to_int(p.get("first_kills")),
            first_deaths=_to_int(p.get("first_deaths")),
        ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_recent_matches(pages: int = 3) -> int:
    """Scrape recent VLR results and insert new matches into the database.

    Returns the number of new matches inserted.
    """
    http = requests.Session()
    http.headers.update(HEADERS)

    # Collect known match IDs
    db = SyncSessionLocal()
    try:
        existing_ids: set[int] = {
            row[0] for row in db.execute(text("SELECT id FROM matches")).fetchall()
        }

        team_cache: dict[str, int] = {
            row[1]: row[0] for row in db.execute(text("SELECT id, name FROM teams")).fetchall()
        }
        player_cache: dict[int, bool] = {
            row[0]: True for row in db.execute(text("SELECT id FROM players")).fetchall()
        }

        new_count = 0

        for page in range(1, pages + 1):
            soup = _fetch(http, f"{RESULTS_URL}/?page={page}")
            page_matches = _parse_results_page(soup)

            if not page_matches:
                logger.info("Empty results page %d, stopping.", page)
                break

            all_known = True
            for match in page_matches:
                if match["match_id"] in existing_ids:
                    continue
                all_known = False

                # Scrape match detail for games + player stats
                logger.info("Scraping match %d: %s vs %s", match["match_id"], match["team1"], match["team2"])
                try:
                    detail_soup = _fetch(http, match["match_url"])
                    games = _extract_games(detail_soup, match)
                    player_rows = _extract_players(detail_soup, match, games)

                    if not games:
                        # Try overview tab
                        detail_soup = _fetch(http, f'{match["match_url"]}?tab=overview')
                        games = _extract_games(detail_soup, match)
                        player_rows = _extract_players(detail_soup, match, games)

                    _insert_match_data(db, match, games, player_rows, team_cache, player_cache)
                    existing_ids.add(match["match_id"])
                    new_count += 1

                    # Be polite
                    time.sleep(1)
                except Exception:
                    logger.exception("Failed to scrape match %d", match["match_id"])
                    continue

            if all_known:
                logger.info("All matches on page %d already known, stopping.", page)
                break

            logger.info("Page %d: found matches, continuing.", page)

        db.commit()
        logger.info("Scrape complete: %d new matches inserted.", new_count)
        return new_count

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

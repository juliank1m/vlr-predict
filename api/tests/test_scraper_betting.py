from pathlib import Path

from bs4 import BeautifulSoup

from app.services.scraper import _parse_betting_section

FIXTURE = Path(__file__).parent / "fixtures" / "vlr_upcoming_match.html"


def test_parse_betting_section_returns_one_row_per_bookmaker():
    soup = BeautifulSoup(FIXTURE.read_text(), "html.parser")
    rows = _parse_betting_section(soup)
    assert len(rows) >= 1
    for r in rows:
        assert isinstance(r["bookmaker"], str) and r["bookmaker"]
        assert r["team1_decimal"] > 1.0
        assert r["team2_decimal"] > 1.0


def test_parse_betting_section_returns_empty_when_no_section():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _parse_betting_section(soup) == []

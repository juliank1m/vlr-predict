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


def test_parse_betting_section_keeps_low_decimal_real_lines():
    """Real lines just above 1.00 (e.g. 1.01) should be kept; only <=1.0 is filtered."""
    soup = BeautifulSoup(FIXTURE.read_text(), "html.parser")
    rows = _parse_betting_section(soup)
    thunderpick = next((r for r in rows if r["bookmaker"] == "thunderpick"), None)
    assert thunderpick is not None
    assert thunderpick["team1_decimal"] == 1.01


def test_parse_betting_section_skips_malformed_odds():
    """Rows whose odds spans contain non-numeric text should be skipped via the ValueError path."""
    html = """
    <a class="match-bet-item" href="#">
      <img class="mod-fakebook" src="/img/pd/fakebook.png" />
      <span class="match-bet-item-odds">N/A</span>
      <span class="match-bet-item-odds">2.5</span>
    </a>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_betting_section(soup) == []

from pathlib import Path

from bs4 import BeautifulSoup

from app.services.scraper import _parse_schedule_page

FIXTURE = Path(__file__).parent / "fixtures" / "vlr_schedule_page.html"


def test_parse_schedule_page_extracts_matches():
    soup = BeautifulSoup(FIXTURE.read_text(), "html.parser")
    matches = _parse_schedule_page(soup)
    assert len(matches) >= 5
    for m in matches:
        assert isinstance(m["match_id"], int)
        assert m["url"].startswith("https://www.vlr.gg/")
        assert m["team1_name"] and m["team2_name"]


def test_parse_schedule_page_returns_empty_for_blank_html():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _parse_schedule_page(soup) == []

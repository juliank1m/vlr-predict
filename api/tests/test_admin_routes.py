"""Smoke tests for admin router wiring."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_admin_odds_route_registered():
    routes = {route.path for route in app.routes}
    assert "/api/admin/odds" in routes


def test_admin_odds_requires_auth():
    resp = client.post("/api/admin/odds")
    assert resp.status_code == 401

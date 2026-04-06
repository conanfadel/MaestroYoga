"""Smoke tests for innovation features router."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import models
from backend.app.database import SessionLocal


def test_metrics_summary_public(client: TestClient) -> None:
    r = client.get("/metrics/summary")
    assert r.status_code == 200
    data = r.json()
    assert "centers" in data
    assert "bookings_total" in data


def test_openapi_lists_feature_paths(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    assert any("/metrics/summary" in p for p in paths)
    assert any("waitlist" in p for p in paths)


def test_calendar_ics_returns_text(client: TestClient) -> None:
    db = SessionLocal()
    name = f"ICS Test Center {int(time.time())}"
    c = models.Center(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    try:
        r = client.get(f"/calendar/centers/{c.id}/sessions.ics")
        assert r.status_code == 200
        assert "BEGIN:VCALENDAR" in r.text
    finally:
        db.delete(c)
        db.commit()
        db.close()


def test_response_time_header(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert "x-response-time-ms" in {k.lower() for k in r.headers.keys()}


def test_my_bookings_redirects_when_not_logged_in(client: TestClient) -> None:
    r = client.get("/public/my-bookings", follow_redirects=False)
    assert r.status_code in (302, 303)

"""Smoke tests for health endpoints used by load balancers and monitoring."""

from __future__ import annotations


def test_health_returns_ok_without_db(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready_returns_ok_with_sqlite(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ready"
    assert data.get("database") == "ok"


def test_api_v1_health_aliases(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

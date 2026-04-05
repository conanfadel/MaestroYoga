"""عمليات التشغيل: صحة، صيانة، معرّفات الطلبات."""

import pytest
from fastapi.testclient import TestClient


def test_health_lightweight(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_api_v1_health_alias(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_api_v1_meta(client: TestClient) -> None:
    r = client.get("/api/v1/meta")
    assert r.status_code == 200
    data = r.json()
    assert data.get("api_version") == "1"
    assert data.get("app") == "Maestro Yoga"
    assert "openapi_json" in data


def test_api_version_headers(client: TestClient) -> None:
    r = client.get("/health", headers={"X-App-Version": "2.0.0-test"})
    assert r.status_code == 200
    assert r.headers.get("X-API-Version") == "1"
    assert r.headers.get("X-App-Version-Accepted") == "2.0.0-test"


def test_health_ready_database(client: TestClient) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ready"
    assert body.get("database") == "ok"


def test_request_id_header_on_response(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert "x-request-id" in {k.lower() for k in r.headers.keys()}
    rid = r.headers.get("X-Request-ID") or r.headers.get("x-request-id")
    assert rid and len(rid) >= 8


def test_request_id_echo_from_client_header(client: TestClient) -> None:
    r = client.get("/health", headers={"X-Request-ID": "client-opaque-id-1"})
    assert r.headers.get("X-Request-ID") == "client-opaque-id-1"


def test_maintenance_mode_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    r = client.get("/index", headers={"Accept": "application/json"}, follow_redirects=False)
    assert r.status_code == 503
    data = r.json()
    assert data.get("error") == "maintenance"


def test_maintenance_mode_html(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    r = client.get("/index", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 503
    assert "جاري التحديث".encode("utf-8") in r.content


def test_health_exempt_when_maintenance(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200

"""مسارات PWA: manifest ديناميكي وعامل الخدمة."""

from fastapi.testclient import TestClient


def test_manifest_json_has_app_version(client: TestClient) -> None:
    from backend.app.app_version import APP_VERSION_STRING

    r = client.get("/manifest.json")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "json" in ct
    data = r.json()
    assert data.get("version") == APP_VERSION_STRING
    assert data.get("name")


def test_service_worker_script_contains_version(client: TestClient) -> None:
    from backend.app.app_version import APP_VERSION_STRING

    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/javascript")
    body = r.text
    assert "maestro-yoga-" in body
    assert APP_VERSION_STRING in body


def test_index_links_dynamic_manifest_and_registers_sw(client: TestClient) -> None:
    from backend.app.app_version import APP_VERSION_STRING

    r = client.get("/index?center_id=1")
    assert r.status_code == 200
    assert f"/manifest.json?v={APP_VERSION_STRING}" in r.text
    assert f"/sw.js?v={APP_VERSION_STRING}" in r.text

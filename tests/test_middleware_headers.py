"""رؤوس الأمان والكاش للملفات الثابتة."""

from fastapi.testclient import TestClient


def test_security_headers_on_api_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "geolocation=()" in (r.headers.get("Permissions-Policy") or "")


def test_static_css_has_cache_control(client: TestClient) -> None:
    r = client.get("/static/css/app-base.css")
    assert r.status_code == 200
    cc = r.headers.get("Cache-Control", "")
    assert "public" in cc
    assert "max-age=" in cc


def test_index_html_includes_versioned_stylesheet(client: TestClient) -> None:
    from backend.app.app_version import APP_VERSION_STRING

    r = client.get("/index?center_id=1")
    assert r.status_code == 200
    assert f"/static/css/index.css?v={APP_VERSION_STRING}" in r.text

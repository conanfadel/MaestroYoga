"""اختبارات وسيط حد الطلبات (يُفعّل فقط داخل هذه الدالة)."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.middleware import clear_rate_limit_buckets_for_tests


def test_strict_auth_posts_return_429_after_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_rate_limit_buckets_for_tests()
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("RATE_LIMIT_STRICT_PER_WINDOW", "3")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SEC", "60")

    client = TestClient(app)
    for _ in range(3):
        r = client.post("/api/v1/auth/login", json={"email": "nope@example.com", "password": "bad"})
        assert r.status_code != 429

    r4 = client.post("/api/v1/auth/login", json={"email": "nope@example.com", "password": "bad"})
    assert r4.status_code == 429
    assert r4.headers.get("Retry-After")
    body = r4.json()
    assert body.get("error") == "rate_limit"


def test_general_requests_not_limited_under_default_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_rate_limit_buckets_for_tests()
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("RATE_LIMIT_GENERAL_PER_WINDOW", "500")

    client = TestClient(app)
    for _ in range(5):
        r = client.get("/api/v1/meta")
        assert r.status_code == 200

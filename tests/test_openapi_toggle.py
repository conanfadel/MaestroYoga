"""سلوك تعطيل وثائق OpenAPI (منطق البيئة دون إعادة تحميل التطبيق بالكامل)."""

import pytest


def test_openapi_json_available_with_default_client(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200


def test_openapi_enabled_respects_production_and_enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app import main as main_mod

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_OPENAPI", raising=False)
    assert main_mod._openapi_enabled() is False

    monkeypatch.setenv("ENABLE_OPENAPI", "1")
    assert main_mod._openapi_enabled() is True

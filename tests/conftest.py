import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_rate_limit_for_tests(monkeypatch) -> None:
    """تفادي فشل الاختبارات بسبب وسيط حد الطلبات (يُفعّل يدوياً في اختبار مخصّص)."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "0")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)

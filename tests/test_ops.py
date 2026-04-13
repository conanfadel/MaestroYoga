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


def test_build_bookings_calendar_ics_contains_vevent() -> None:
    from backend.app.checkout_finalize.payment_notifications import build_bookings_calendar_ics
    from backend.app.models.commerce import Booking
    from backend.app.models.schedule import YogaSession
    from backend.app.time_utils import utcnow_naive

    start = utcnow_naive()
    b = Booking(id=99, center_id=1, session_id=1, client_id=1, status="confirmed")
    s = YogaSession(
        id=1,
        center_id=1,
        room_id=1,
        title="Test Session",
        trainer_name="Coach",
        level="beginner",
        starts_at=start,
        duration_minutes=45,
        price_drop_in=40.0,
    )
    raw = build_bookings_calendar_ics(center_name="Test Center", booking_sessions=[(b, s)])
    assert b"BEGIN:VCALENDAR" in raw
    assert b"BEGIN:VEVENT" in raw
    assert b"maestro-booking-99" in raw


def test_normalize_paymob_iframe_strips_paymob_placeholder_token() -> None:
    from backend.app.payments.paymob_provider import normalize_paymob_iframe_checkout_base

    raw = "https://ksa.paymob.com/api/acceptance/iframes/10190?payment_token={payment_key_obtained_previously}"
    assert normalize_paymob_iframe_checkout_base(raw) == "https://ksa.paymob.com/api/acceptance/iframes/10190"


def test_empty_public_subscription_context_has_book_url() -> None:
    from backend.app.public_subscription_helpers import empty_public_subscription_context

    ctx = empty_public_subscription_context(3)
    assert ctx["public_sub_active"] is False
    assert ctx["public_sub_plan_slot_booking"] is False
    assert ctx["public_sub_book_url"] == "/index?center_id=3#sessions-section"


def test_yoga_session_visibility_end_and_booking_rules() -> None:
    from datetime import timedelta

    from backend.app.models.schedule import YogaSession
    from backend.app.public_session_visibility import (
        yoga_session_accepts_new_public_booking,
        yoga_session_end_naive,
        yoga_session_still_on_public_schedule,
    )
    from backend.app.time_utils import utcnow_naive

    now = utcnow_naive()
    s = YogaSession(
        center_id=1,
        room_id=1,
        title="t",
        trainer_name="x",
        level="beginner",
        starts_at=now - timedelta(hours=2),
        duration_minutes=60,
        price_drop_in=10.0,
    )
    assert yoga_session_still_on_public_schedule(s, now=now) is False
    assert yoga_session_accepts_new_public_booking(s, now=now) is False
    s2 = YogaSession(
        center_id=1,
        room_id=1,
        title="t",
        trainer_name="x",
        level="beginner",
        starts_at=now + timedelta(hours=1),
        duration_minutes=60,
        price_drop_in=10.0,
    )
    assert yoga_session_still_on_public_schedule(s2, now=now) is True
    assert yoga_session_accepts_new_public_booking(s2, now=now) is True
    end = yoga_session_end_naive(s2)
    assert end == s2.starts_at + timedelta(minutes=60)


def test_build_public_active_subscription_without_user_returns_empty() -> None:
    from backend.app.database import SessionLocal
    from backend.app.public_subscription_helpers import build_public_active_subscription_context

    db = SessionLocal()
    try:
        ctx = build_public_active_subscription_context(db, 1, None, {"weekly": "أسبوعي"})
        assert ctx["public_sub_active"] is False
    finally:
        db.close()


def test_checkout_status_signature_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "unit-test-checkout-status-secret")
    from backend.app.checkout_status_urls import (
        build_checkout_status_url,
        checkout_status_signature,
        verify_checkout_status_signature,
    )

    assert verify_checkout_status_signature(1, [9, 5], checkout_status_signature(1, [5, 9]))
    assert not verify_checkout_status_signature(1, [5], checkout_status_signature(1, [5, 9]))
    url = build_checkout_status_url("https://example.test", 2, [100], result="cancelled")
    assert url.startswith("https://example.test/checkout-status?")
    assert "center_id=2" in url
    assert "payment_id=100" in url
    assert "result=cancelled" in url
    assert "sig=" in url


def test_checkout_status_page_invalid_link(client: TestClient) -> None:
    r = client.get("/checkout-status")
    assert r.status_code == 200
    assert "غير صالح" in r.text


def test_checkout_status_clean_redirect_keeps_success_param(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_SECRET", "redirect-test-secret-checkout-status")
    from urllib.parse import unquote

    from backend.app.checkout_status_urls import checkout_status_signature

    sig = checkout_status_signature(1, [50])
    r = client.get(
        f"/checkout-status?center_id=1&payment_id=50&sig={sig}&success=false&hmac=noise&order=999",
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "")
    assert "success=false" in loc
    assert "hmac=noise" not in loc


def test_checkout_status_clean_redirect_keeps_txn_response_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_SECRET", "redirect-test-secret-checkout-status-txn")
    from urllib.parse import unquote

    from backend.app.checkout_status_urls import checkout_status_signature

    sig = checkout_status_signature(1, [51])
    r = client.get(
        f"/checkout-status?center_id=1&payment_id=51&sig={sig}&txn_response_code=DECLINED&junk=1",
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "")
    assert "txn_response_code=DECLINED" in loc
    assert "junk=1" not in loc


def test_paymob_webhook_accepts_hmac_in_query_string(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """بعض إعدادات Paymob تُرسل توقيع hmac في ?hmac= بدل جسم JSON."""
    monkeypatch.setenv("PAYMOB_HMAC_SECRET", "test-secret-paymob-webhook-query")
    import backend.app.main_webhooks as mw

    monkeypatch.setattr(mw, "verify_paymob_processed_hmac", lambda payload, received, secret: True)
    called: list[str] = []
    monkeypatch.setattr(mw, "finalize_checkout_paid", lambda *a, **k: called.append("paid"))
    monkeypatch.setattr(mw, "finalize_checkout_failed", lambda *a, **k: called.append("failed"))

    body = {
        "obj": {
            "success": True,
            "amount_cents": 100,
            "currency": "SAR",
            "order": {"id": 999},
            "merchant_order_id": "mP1",
        }
    }
    r = client.post("/payments/webhook/paymob?hmac=" + "ab" * 64, json=body)
    assert r.status_code == 200
    assert r.json().get("received") is True
    assert called == ["paid"]

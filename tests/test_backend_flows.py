import time

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.mailer import validate_mailer_settings
from backend.app.security import create_public_email_verification_token, hash_password
from backend.app.web_shared import (
    _mail_fail_reason_query_token,
    public_center_id_str_from_next,
    public_index_url_from_next,
    public_mail_fail_why_token,
)


def test_verify_email_redirects_invalid_token(client):
    response = client.get("/public/verify-email?token=bad&next=/index?center_id=1", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/public/verify-pending")


def test_reset_password_redirects_invalid_token(client):
    response = client.post(
        "/public/reset-password",
        data={"token": "bad", "password": "Admin@12345", "confirm_password": "Admin@12345"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/public/login?")
    assert "msg=invalid_reset_link" in location


def test_reset_password_page_without_token_shows_hint(client):
    response = client.get("/public/reset-password", follow_redirects=False)
    assert response.status_code == 200
    body = response.text
    assert "الرابط غير مكتمل" in body or "طلب رابط" in body


def test_mail_fail_reason_query_token_sanitizes():
    assert _mail_fail_reason_query_token("missing_resend_api_key") == "missing_resend_api_key"
    assert _mail_fail_reason_query_token("") == ""
    assert _mail_fail_reason_query_token("bad;drop") == ""
    assert _mail_fail_reason_query_token("123x") == ""


def test_public_index_url_from_next():
    assert public_index_url_from_next("/index?center_id=3", msg="email_verified") == "/index?center_id=3&msg=email_verified"
    assert public_index_url_from_next("/post?center_id=2&post_id=1") == "/index?center_id=2"
    assert public_index_url_from_next(None) == "/index?center_id=1"
    assert public_center_id_str_from_next("/index?center_id=5") == "5"


def test_public_mail_fail_why_token_maps_resend_sandbox_403():
    raw = (
        'resend_http_403:{"statusCode":403,"name":"validation_error",'
        '"message":"You can only send testing emails to your own email address. '
        'To send emails to other recipients, please verify a domain"}'
    )
    assert public_mail_fail_why_token(raw) == "resend_sandbox_domain"
    assert public_mail_fail_why_token("missing_resend_api_key") == "missing_resend_api_key"


def test_validate_mailer_resend_requires_api_key(monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    ok, reason = validate_mailer_settings()
    assert ok is False
    assert reason == "missing_resend_api_key"
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM", "onboarding@resend.dev")
    ok2, reason2 = validate_mailer_settings()
    assert ok2 is True
    assert reason2 == "ok"


def test_email_confirmed_page_shows_redirect_hint(client):
    r = client.get("/public/email-confirmed?center_id=1")
    assert r.status_code == 200
    assert "تم تأكيد البريد" in r.text
    assert "/index?center_id=1&amp;msg=email_verified" in r.text or "center_id=1" in r.text


def test_verify_email_marks_user_verified(client):
    db = SessionLocal()
    email = f"pytest_verify_{int(time.time())}@example.com"
    user = models.PublicUser(
        full_name="Pytest Verify",
        email=email,
        phone="+966500000010",
        password_hash=hash_password("Admin@12345"),
        email_verified=False,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_public_email_verification_token(user.id, user.email)

    response = client.get(f"/public/verify-email?token={token}&next=/index?center_id=1", follow_redirects=False)
    db.refresh(user)

    assert response.status_code == 303
    assert response.headers["location"] == "/public/email-confirmed?center_id=1"
    assert user.email_verified is True

    db.delete(user)
    db.commit()
    db.close()

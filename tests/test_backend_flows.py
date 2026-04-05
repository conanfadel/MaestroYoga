import time

from fastapi.testclient import TestClient

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.mailer import validate_mailer_settings
from backend.app.security import create_public_email_verification_token, hash_password
from backend.app.web_shared import (
    _mail_fail_reason_query_token,
    PUBLIC_INDEX_DEFAULT_PATH,
    public_center_id_str_from_next,
    public_index_url_from_next,
    public_mail_fail_why_token,
)


def test_public_account_redirects_when_not_logged_in(client):
    r = client.get(f"/public/account?next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/public/login?")


def test_public_account_updates_name_and_phone(client):
    db = SessionLocal()
    email = f"pytest_acct_{int(time.time())}@example.com"
    user = models.PublicUser(
        full_name="Before Name",
        email=email,
        phone="+966500000099",
        password_hash=hash_password("Admin@12345"),
        email_verified=True,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    client.post(
        "/public/login",
        data={"email": email, "password": "Admin@12345", "next": PUBLIC_INDEX_DEFAULT_PATH},
        follow_redirects=False,
    )
    r2 = client.post(
        "/public/account",
        data={
            "full_name": "After Name",
            "country_code": "+966",
            "phone": "501112233",
            "next": PUBLIC_INDEX_DEFAULT_PATH,
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "msg=saved" in r2.headers["location"]
    db.refresh(user)
    assert user.full_name == "After Name"
    assert user.phone == "+966501112233"
    db.delete(user)
    db.commit()
    db.close()


def test_verify_email_redirects_invalid_token(client):
    response = client.get(
        f"/public/verify-email?token=bad&next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False
    )
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
    assert public_index_url_from_next(None) == PUBLIC_INDEX_DEFAULT_PATH
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


def test_verify_email_then_verify_pending_shows_success_and_index_link(client):
    db = SessionLocal()
    email = f"pytest_vp_ok_{int(time.time())}@example.com"
    user = models.PublicUser(
        full_name="Pytest VP",
        email=email,
        phone="+966500000011",
        password_hash=hash_password("Admin@12345"),
        email_verified=False,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_public_email_verification_token(user.id, user.email)
    r1 = client.get(f"/public/verify-email?token={token}&next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False)
    assert r1.status_code == 303
    loc = r1.headers["location"]
    assert "/public/verify-pending" in loc
    assert "msg=email_verified" in loc
    assert "vk=" in loc
    assert "next=" in loc
    r2 = client.get(loc, follow_redirects=False)
    assert r2.status_code == 200
    assert "تم تفعيل حسابك" in r2.text
    assert "center_id=1" in r2.text and "msg=email_verified" in r2.text
    db.delete(user)
    db.commit()
    db.close()


def test_verify_pending_success_shows_without_session_cookie_using_vk(client):
    """Opening the post-verify URL in a fresh browser (no cookie) must not send users to login."""
    db = SessionLocal()
    email = f"pytest_vp_vk_{int(time.time())}@example.com"
    user = models.PublicUser(
        full_name="Pytest VK",
        email=email,
        phone="+966500000012",
        password_hash=hash_password("Admin@12345"),
        email_verified=False,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_public_email_verification_token(user.id, user.email)
    r1 = client.get(f"/public/verify-email?token={token}&next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False)
    assert r1.status_code == 303
    loc = r1.headers["location"]
    assert "vk=" in loc
    fresh = TestClient(app)
    r2 = fresh.get(loc, follow_redirects=False)
    assert r2.status_code == 200
    assert "تم تفعيل حسابك" in r2.text
    assert "الواجهة الرئيسية" in r2.text
    db.delete(user)
    db.commit()
    db.close()


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

    response = client.get(
        f"/public/verify-email?token={token}&next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False
    )
    db.refresh(user)

    assert response.status_code == 303
    loc = response.headers["location"]
    assert loc.startswith("/public/verify-pending?")
    assert "msg=email_verified" in loc
    assert "next=%2Findex%3Fcenter_id%3D1" in loc or "next=" in loc
    assert user.email_verified is True

    db.delete(user)
    db.commit()
    db.close()


def test_public_news_list_page_ok(client):
    r = client.get("/news?center_id=1")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "أخبار وإعلانات" in body or "لا توجد أخبار" in body


def test_public_news_list_filter_and_sort(client):
    r = client.get("/news?center_id=1&type=news&sort=oldest")
    assert r.status_code == 200
    assert "نوع المنشور" in r.text
    assert "الترتيب" in r.text

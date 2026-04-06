"""FCM registration and notification preferences API."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.security import create_public_access_token, hash_password


def test_push_preferences_requires_auth(client: TestClient) -> None:
    r = client.get("/push/preferences")
    assert r.status_code == 401


def test_openapi_lists_push_paths(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    assert any("/push/" in p for p in paths)


def test_push_register_and_preferences_with_bearer(client: TestClient) -> None:
    db = SessionLocal()
    email = f"pytest_push_{int(time.time())}@example.com"
    user = models.PublicUser(
        full_name="Push Test",
        email=email,
        phone=None,
        password_hash=hash_password("Admin@12345"),
        email_verified=True,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_public_access_token(user.id)
    try:
        h = {"Authorization": f"Bearer {token}"}
        tok = "a" * 142 + "pytest_fcm_suffix"
        r1 = client.post("/push/register", json={"fcm_token": tok, "platform": "android"}, headers=h)
        assert r1.status_code == 200
        r2 = client.get("/push/preferences", headers=h)
        assert r2.status_code == 200
        assert r2.json().get("push_enabled") is True
        r3 = client.patch("/push/preferences", json={"push_reminders": False}, headers=h)
        assert r3.status_code == 200
        assert r3.json().get("push_reminders") is False
        r4 = client.post("/push/unregister", json={"fcm_token": tok}, headers=h)
        assert r4.status_code == 200
        assert r4.json().get("removed") == 1
    finally:
        db.query(models.PublicPushDevice).filter(models.PublicPushDevice.public_user_id == user.id).delete(
            synchronize_session=False
        )
        db.delete(user)
        db.commit()
        db.close()

import time
from datetime import timedelta

from backend.app import models
from backend.app.bootstrap import ensure_demo_data
from backend.app.checkout_finalize import (
    expire_stale_pending_payments,
    finalize_checkout_paid,
    finalize_payment_refunded,
)
from backend.app.database import SessionLocal
from backend.app.security import hash_password
from backend.app.time_utils import utcnow_naive


def test_admin_login_create_delete_room(client):
    login_page = client.get("/admin/login")
    assert login_page.status_code == 200

    login = client.post(
        "/admin/login",
        data={"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/admin"

    room_name = f"Pytest Room {int(time.time())}"
    create_room = client.post(
        "/admin/rooms",
        data={"name": room_name, "capacity": "9"},
        follow_redirects=False,
    )
    assert create_room.status_code == 303
    assert create_room.headers["location"].startswith("/admin?msg=room_created")

    db = SessionLocal()
    room = db.query(models.Room).filter(models.Room.name == room_name).order_by(models.Room.id.desc()).first()
    assert room is not None
    room_id = room.id
    db.close()

    delete_room = client.post(
        "/admin/rooms/delete",
        data={"room_id": str(room_id), "scroll_y": "0"},
        follow_redirects=False,
    )
    assert delete_room.status_code == 303
    assert delete_room.headers["location"].startswith("/admin?msg=room_deleted")


def test_admin_center_post_remote_cover_and_gallery_urls(client):
    login = client.post(
        "/admin/login",
        data={"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    title = f"Pytest Remote Images Post {int(time.time())}"
    cover = "https://picsum.photos/seed/pytest-post-cover/800/450"
    g1 = "https://picsum.photos/seed/pytest-post-g1/400/300"
    g2 = "https://picsum.photos/seed/pytest-post-g2/400/300"
    save = client.post(
        "/admin/center/posts/save",
        data={
            "title": title,
            "post_type": "news",
            "summary": "اختبار روابط الصور",
            "body": "نص تجريبي",
            "is_published": "1",
            "cover_remote_url": cover,
            "gallery_remote_urls": f"{g1}\n{g2}, ",
        },
        follow_redirects=False,
    )
    assert save.status_code == 303
    assert "center_post_saved" in (save.headers.get("location") or "")

    db = SessionLocal()
    post = (
        db.query(models.CenterPost)
        .filter(models.CenterPost.title == title)
        .order_by(models.CenterPost.id.desc())
        .first()
    )
    assert post is not None
    assert post.cover_image_url == cover
    urls = [
        img.image_url
        for img in sorted(post.images, key=lambda x: (x.sort_order, x.id))
    ]
    assert urls == [g1, g2]
    db.close()

    detail = client.get(f"/post?center_id={post.center_id}&post_id={post.id}")
    assert detail.status_code == 200
    assert cover in detail.text

    client.post(
        "/admin/center/posts/delete",
        data={"post_id": str(post.id)},
        follow_redirects=False,
    )


def test_admin_center_branding_upload_and_tagline(client):
    login = client.post(
        "/admin/login",
        data={"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    db = SessionLocal()
    owner = db.query(models.User).filter(models.User.email == "owner@maestroyoga.local").first()
    assert owner is not None
    center_id = owner.center_id
    db.close()

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    save = client.post(
        "/admin/center/branding",
        data={"brand_tagline": "نص تجريبي للهوية", "scroll_y": "0"},
        files={"logo": ("mark.png", png_bytes, "image/png")},
        follow_redirects=False,
    )
    assert save.status_code == 303
    assert "msg=center_branding_updated" in (save.headers.get("location") or "")

    db = SessionLocal()
    center = db.get(models.Center, center_id)
    assert center is not None
    assert center.brand_tagline == "نص تجريبي للهوية"
    assert center.logo_url and f"center_{center_id}.png" in center.logo_url
    db.close()

    hero_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    hero_save = client.post(
        "/admin/center/branding",
        data={"scroll_y": "0"},
        files={"hero": ("studio.jpg", hero_png, "image/jpeg")},
        follow_redirects=False,
    )
    assert hero_save.status_code == 303
    assert "msg=center_branding_updated" in (hero_save.headers.get("location") or "")
    db = SessionLocal()
    center = db.get(models.Center, center_id)
    assert center is not None
    assert center.hero_image_url and f"center_{center_id}_hero.jpg" in center.hero_image_url
    assert center.hero_show_stock_photo is False
    db.close()

    rm_hero = client.post(
        "/admin/center/branding",
        data={"scroll_y": "0", "remove_hero": "1"},
        follow_redirects=False,
    )
    assert rm_hero.status_code == 303
    db = SessionLocal()
    center = db.get(models.Center, center_id)
    assert center is not None
    assert center.hero_image_url is None
    assert center.hero_show_stock_photo is False
    db.close()

    restore = client.post(
        "/admin/center/branding",
        data={"scroll_y": "0", "restore_hero_stock": "1"},
        follow_redirects=False,
    )
    assert restore.status_code == 303
    db = SessionLocal()
    center = db.get(models.Center, center_id)
    assert center is not None
    assert center.hero_image_url is None
    assert center.hero_show_stock_photo is True
    db.close()

    bad = client.post(
        "/admin/center/branding",
        data={"scroll_y": "0"},
        files={"logo": ("x.exe", b"MZ", "application/octet-stream")},
        follow_redirects=False,
    )
    assert bad.status_code == 303
    assert "msg=center_branding_bad_file" in (bad.headers.get("location") or "")

    custom_heading = "عنوان مخصص للهيرو | تجربة"
    hero_title = client.post(
        "/admin/center/branding",
        data={"scroll_y": "0", "brand_tagline": "", "index_hero_heading": custom_heading},
        follow_redirects=False,
    )
    assert hero_title.status_code == 303
    db = SessionLocal()
    center = db.get(models.Center, center_id)
    assert center is not None
    assert center.index_hero_heading_override == custom_heading
    db.close()

    hero_reset = client.post(
        "/admin/center/branding",
        data={"scroll_y": "0", "brand_tagline": "", "reset_index_hero_heading": "1"},
        follow_redirects=False,
    )
    assert hero_reset.status_code == 303
    db = SessionLocal()
    center = db.get(models.Center, center_id)
    assert center is not None
    assert center.index_hero_heading_override is None
    db.close()


def test_mobile_compatible_api_flow(client):
    db = SessionLocal()
    ensure_demo_data(db)
    db.close()

    auth_response = client.post("/auth/login", json={"email": "owner@maestroyoga.local", "password": "Admin@12345"})
    assert auth_response.status_code == 200
    token = auth_response.json()["access_token"]
    refresh = auth_response.json()["refresh_token"]
    assert refresh
    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200
    refreshed_token = refreshed.json()["access_token"]
    assert refreshed_token
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/dashboard/summary", headers=headers).status_code == 200
    sessions_response = client.get("/sessions", headers=headers)
    assert sessions_response.status_code == 200
    assert client.get("/clients", headers=headers).status_code == 200
    assert client.get("/payments", headers=headers).status_code == 200

    sessions = sessions_response.json()
    assert sessions
    session_id = sessions[0]["id"]

    unique_email = f"pytest_mobile_{int(time.time())}@example.com"
    created_client = client.post(
        "/clients",
        json={"full_name": "Pytest Mobile", "email": unique_email, "phone": "+966500000011"},
        headers=headers,
    )
    assert created_client.status_code == 200
    created_client_id = created_client.json()["id"]

    booking = client.post(
        "/bookings",
        json={"session_id": session_id, "client_id": created_client_id},
        headers=headers,
    )
    assert booking.status_code == 200

    payment = client.post(
        "/payments",
        json={"client_id": created_client_id, "amount": 60, "currency": "SAR", "payment_method": "in_app_mock"},
        headers=headers,
    )
    assert payment.status_code == 200

    db = SessionLocal()
    db.query(models.Payment).filter(models.Payment.client_id == created_client_id).delete(synchronize_session=False)
    db.query(models.Booking).filter(models.Booking.client_id == created_client_id).delete(synchronize_session=False)
    db.query(models.Client).filter(models.Client.id == created_client_id).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_admin_logout_requires_post_and_clears_cookie(client):
    login = client.post(
        "/admin/login",
        data={"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/admin"

    get_logout = client.get("/admin/logout", follow_redirects=False)
    assert get_logout.status_code == 405

    post_logout = client.post("/admin/logout", follow_redirects=False)
    assert post_logout.status_code == 303
    assert post_logout.headers["location"] == "/admin/login"


def test_finalize_checkout_paid_is_idempotent(client, monkeypatch):
    monkeypatch.setenv("DISABLE_PAYMENT_SUCCESS_EMAIL", "1")
    db = SessionLocal()
    stamp = int(time.time())
    center = models.Center(name=f"Pytest Center {stamp}", city="Riyadh")
    db.add(center)
    db.flush()
    room = models.Room(center_id=center.id, name=f"Room {stamp}", capacity=8)
    db.add(room)
    db.flush()
    yoga_session = models.YogaSession(
        center_id=center.id,
        room_id=room.id,
        title="Session",
        trainer_name="Trainer",
        level="beginner",
        starts_at=utcnow_naive() + timedelta(days=1),
        duration_minutes=60,
        price_drop_in=50.0,
    )
    db.add(yoga_session)
    db.flush()
    client_row = models.Client(center_id=center.id, full_name="Pytest User", email=f"pytest_{stamp}@example.com")
    db.add(client_row)
    db.flush()
    booking = models.Booking(
        center_id=center.id,
        session_id=yoga_session.id,
        client_id=client_row.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()
    payment = models.Payment(
        center_id=center.id,
        client_id=client_row.id,
        booking_id=booking.id,
        amount=50.0,
        currency="SAR",
        payment_method="public_checkout",
        provider_ref=f"pytest_ref_{stamp}",
        status="pending",
        created_at=utcnow_naive(),
    )
    db.add(payment)
    db.commit()

    meta = {"payment_id": str(payment.id), "booking_id": str(booking.id), "center_id": str(center.id)}
    finalize_checkout_paid(db, meta, payment.provider_ref or "")
    finalize_checkout_paid(db, meta, payment.provider_ref or "")

    db.refresh(payment)
    db.refresh(booking)
    assert payment.status == "paid"
    assert booking.status == "confirmed"

    db.delete(payment)
    db.delete(booking)
    db.delete(client_row)
    db.delete(yoga_session)
    db.delete(room)
    db.delete(center)
    db.commit()
    db.close()


def test_admin_cannot_manage_public_user_of_another_center(client):
    db = SessionLocal()
    ensure_demo_data(db)
    other_center = models.Center(name=f"Other Center {int(time.time())}", city="Jeddah")
    db.add(other_center)
    db.flush()

    email = f"pytest_cross_center_{int(time.time())}@example.com"
    outsider_public_user = models.PublicUser(
        full_name="Cross Center User",
        email=email,
        phone=f"+9665{int(time.time()) % 100000000:08d}",
        password_hash=hash_password("Admin@12345"),
        is_active=True,
        is_deleted=False,
        email_verified=True,
    )
    db.add(outsider_public_user)
    db.flush()

    # Link the public user only to the other center via Client email mapping.
    other_client = models.Client(
        center_id=other_center.id,
        full_name="Linked Other Client",
        email=email,
        phone="+966500000123",
    )
    db.add(other_client)
    db.commit()
    outsider_id = outsider_public_user.id

    login = client.post(
        "/admin/login",
        data={"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/admin"

    resp = client.post(
        "/admin/public-users/toggle-active",
        data={"public_user_id": str(outsider_id), "scroll_y": "0"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "msg=public_user_not_found" in (resp.headers.get("location") or "")

    db.refresh(outsider_public_user)
    assert outsider_public_user.is_active is True

    db.delete(other_client)
    db.delete(outsider_public_user)
    db.delete(other_center)
    db.commit()
    db.close()


def test_finalize_checkout_paid_rejects_amount_mismatch(monkeypatch):
    monkeypatch.setenv("DISABLE_PAYMENT_SUCCESS_EMAIL", "1")
    db = SessionLocal()
    stamp = int(time.time())
    center = models.Center(name=f"Pytest Center amt {stamp}", city="Riyadh")
    db.add(center)
    db.flush()
    room = models.Room(center_id=center.id, name=f"Room {stamp}", capacity=8)
    db.add(room)
    db.flush()
    yoga_session = models.YogaSession(
        center_id=center.id,
        room_id=room.id,
        title="Session",
        trainer_name="Trainer",
        level="beginner",
        starts_at=utcnow_naive() + timedelta(days=1),
        duration_minutes=60,
        price_drop_in=50.0,
    )
    db.add(yoga_session)
    db.flush()
    client_row = models.Client(center_id=center.id, full_name="Pytest User", email=f"pytest_amt_{stamp}@example.com")
    db.add(client_row)
    db.flush()
    booking = models.Booking(
        center_id=center.id,
        session_id=yoga_session.id,
        client_id=client_row.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()
    payment = models.Payment(
        center_id=center.id,
        client_id=client_row.id,
        booking_id=booking.id,
        amount=50.0,
        currency="SAR",
        payment_method="public_checkout",
        provider_ref=f"pytest_ref_amt_{stamp}",
        status="pending",
        created_at=utcnow_naive(),
    )
    db.add(payment)
    db.commit()

    meta = {"payment_id": str(payment.id), "booking_id": str(booking.id), "center_id": str(center.id)}
    finalize_checkout_paid(
        db,
        meta,
        payment.provider_ref or "",
        amount_total_minor=999999,
        currency_from_provider="sar",
    )
    db.refresh(payment)
    db.refresh(booking)
    assert payment.status == "failed"
    assert booking.status == "cancelled"

    db.delete(payment)
    db.delete(booking)
    db.delete(client_row)
    db.delete(yoga_session)
    db.delete(room)
    db.delete(center)
    db.commit()
    db.close()


def test_finalize_payment_refunded_after_paid(monkeypatch):
    monkeypatch.setenv("DISABLE_PAYMENT_SUCCESS_EMAIL", "1")
    db = SessionLocal()
    stamp = int(time.time())
    center = models.Center(name=f"Pytest Center rf {stamp}", city="Riyadh")
    db.add(center)
    db.flush()
    room = models.Room(center_id=center.id, name=f"Room {stamp}", capacity=8)
    db.add(room)
    db.flush()
    yoga_session = models.YogaSession(
        center_id=center.id,
        room_id=room.id,
        title="Session",
        trainer_name="Trainer",
        level="beginner",
        starts_at=utcnow_naive() + timedelta(days=1),
        duration_minutes=60,
        price_drop_in=50.0,
    )
    db.add(yoga_session)
    db.flush()
    client_row = models.Client(center_id=center.id, full_name="Pytest User", email=f"pytest_rf_{stamp}@example.com")
    db.add(client_row)
    db.flush()
    booking = models.Booking(
        center_id=center.id,
        session_id=yoga_session.id,
        client_id=client_row.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()
    payment = models.Payment(
        center_id=center.id,
        client_id=client_row.id,
        booking_id=booking.id,
        amount=50.0,
        currency="SAR",
        payment_method="public_checkout",
        provider_ref=f"pytest_ref_rf_{stamp}",
        status="pending",
        created_at=utcnow_naive(),
    )
    db.add(payment)
    db.commit()

    meta = {"payment_id": str(payment.id), "booking_id": str(booking.id), "center_id": str(center.id)}
    finalize_checkout_paid(
        db,
        meta,
        payment.provider_ref or "",
        amount_total_minor=5000,
        currency_from_provider="sar",
    )
    finalize_payment_refunded(db, meta, payment.provider_ref or "")
    db.refresh(payment)
    db.refresh(booking)
    assert payment.status == "refunded"
    assert booking.status == "cancelled"

    db.delete(payment)
    db.delete(booking)
    db.delete(client_row)
    db.delete(yoga_session)
    db.delete(room)
    db.delete(center)
    db.commit()
    db.close()


def test_expire_stale_pending_payments_cleans_booking():
    db = SessionLocal()
    stamp = int(time.time())
    center = models.Center(name=f"Pytest Center stale {stamp}", city="Riyadh")
    db.add(center)
    db.flush()
    room = models.Room(center_id=center.id, name=f"Room {stamp}", capacity=8)
    db.add(room)
    db.flush()
    yoga_session = models.YogaSession(
        center_id=center.id,
        room_id=room.id,
        title="Session",
        trainer_name="Trainer",
        level="beginner",
        starts_at=utcnow_naive() + timedelta(days=1),
        duration_minutes=60,
        price_drop_in=50.0,
    )
    db.add(yoga_session)
    db.flush()
    client_row = models.Client(center_id=center.id, full_name="Pytest User", email=f"pytest_stale_{stamp}@example.com")
    db.add(client_row)
    db.flush()
    booking = models.Booking(
        center_id=center.id,
        session_id=yoga_session.id,
        client_id=client_row.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()
    payment = models.Payment(
        center_id=center.id,
        client_id=client_row.id,
        booking_id=booking.id,
        amount=50.0,
        currency="SAR",
        payment_method="public_checkout",
        provider_ref=None,
        status="pending",
        created_at=utcnow_naive() - timedelta(hours=4),
    )
    db.add(payment)
    db.commit()
    pid = payment.id
    bid = booking.id

    n = expire_stale_pending_payments(db, older_than_minutes=60)
    assert n >= 1

    payment = db.get(models.Payment, pid)
    booking = db.get(models.Booking, bid)
    assert payment.status == "failed"
    assert booking.status == "cancelled"

    db.delete(payment)
    db.delete(booking)
    db.delete(client_row)
    db.delete(yoga_session)
    db.delete(room)
    db.delete(center)
    db.commit()
    db.close()

import time

from backend.app import models
from backend.app.bootstrap import ensure_demo_data
from backend.app.database import SessionLocal


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


def test_mobile_compatible_api_flow(client):
    db = SessionLocal()
    ensure_demo_data(db)
    db.close()

    auth_response = client.post("/auth/login", json={"email": "owner@maestroyoga.local", "password": "Admin@12345"})
    assert auth_response.status_code == 200
    token = auth_response.json()["access_token"]
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

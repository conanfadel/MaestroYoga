import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import models
from backend.app.bootstrap import ensure_demo_data
from backend.app.database import SessionLocal
from backend.app.main import app


def main() -> None:
    client = TestClient(app)
    db = SessionLocal()
    ensure_demo_data(db)
    db.close()

    auth_resp = client.post("/auth/login", json={"email": "owner@maestroyoga.local", "password": "Admin@12345"})
    auth_data = auth_resp.json()
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("auth_login", auth_resp.status_code)

    summary = client.get("/dashboard/summary", headers=headers)
    sessions = client.get("/sessions", headers=headers)
    clients = client.get("/clients", headers=headers)
    payments = client.get("/payments", headers=headers)
    print("dashboard", summary.status_code, "sessions", sessions.status_code, "clients", clients.status_code, "payments", payments.status_code)

    sessions_json = sessions.json()
    if not sessions_json:
        print("mobile_flow_skipped", "no_sessions")
        return

    unique_email = f"mobile_smoke_{int(time.time())}@example.com"
    created_client = client.post(
        "/clients",
        json={"full_name": "Mobile Smoke", "email": unique_email, "phone": "+966500000003"},
        headers=headers,
    )
    client_json = created_client.json()
    booking = client.post(
        "/bookings",
        json={"session_id": sessions_json[0]["id"], "client_id": client_json["id"]},
        headers=headers,
    )
    payment = client.post(
        "/payments",
        json={"client_id": client_json["id"], "amount": 60, "currency": "SAR", "payment_method": "in_app_mock"},
        headers=headers,
    )
    print("mobile_create_client", created_client.status_code, "booking", booking.status_code, "payment", payment.status_code)

    # Cleanup temporary rows to keep DB tidy.
    db = SessionLocal()
    db.query(models.Payment).filter(models.Payment.client_id == client_json["id"]).delete(synchronize_session=False)
    db.query(models.Booking).filter(models.Booking.client_id == client_json["id"]).delete(synchronize_session=False)
    db.query(models.Client).filter(models.Client.id == client_json["id"]).delete(synchronize_session=False)
    db.commit()
    db.close()


if __name__ == "__main__":
    main()

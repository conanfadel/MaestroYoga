import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app import models


def main() -> None:
    client = TestClient(app)

    login_page = client.get("/admin/login")
    print("admin_login_page", login_page.status_code)

    login = client.post(
        "/admin/login",
        data={"email": "owner@maestroyoga.local", "password": "Admin@12345"},
        follow_redirects=False,
    )
    print("admin_login_post", login.status_code, login.headers.get("location"))

    room_name = f"QA Smoke Room {int(time.time())}"
    create_room = client.post(
        "/admin/rooms",
        data={"name": room_name, "capacity": "7"},
        follow_redirects=False,
    )
    print("admin_room_create", create_room.status_code, create_room.headers.get("location"))

    db = SessionLocal()
    room = db.query(models.Room).filter(models.Room.name == room_name).order_by(models.Room.id.desc()).first()
    room_id = room.id if room else None
    print("admin_room_created_id", room_id)
    db.close()

    if room_id:
        delete_room = client.post(
            "/admin/rooms/delete",
            data={"room_id": str(room_id), "scroll_y": "0"},
            follow_redirects=False,
        )
        print("admin_room_delete", delete_room.status_code, delete_room.headers.get("location"))


if __name__ == "__main__":
    main()

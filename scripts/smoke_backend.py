import time
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import models
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.security import create_public_email_verification_token, hash_password
from backend.app.web_shared import PUBLIC_INDEX_DEFAULT_PATH


def main() -> None:
    client = TestClient(app)

    # 1) Invalid verification link should redirect safely.
    verify_bad = client.get(
        f"/public/verify-email?token=bad&next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False
    )
    print("verify_bad", verify_bad.status_code, verify_bad.headers.get("location"))

    # 2) Invalid reset token should redirect to login (no raw traceback for users).
    reset_bad = client.post(
        "/public/reset-password",
        data={"token": "bad", "password": "Admin@12345", "confirm_password": "Admin@12345"},
        follow_redirects=False,
    )
    print("reset_bad", reset_bad.status_code, reset_bad.headers.get("location"))

    # 3) Valid verification token should verify the user and redirect to next URL.
    db = SessionLocal()
    email = f"smoke_{int(time.time())}@example.com"
    user = models.PublicUser(
        full_name="Smoke Test",
        email=email,
        phone="+966500000002",
        password_hash=hash_password("Admin@12345"),
        email_verified=False,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_public_email_verification_token(user.id, user.email)
    verify_ok = client.get(
        f"/public/verify-email?token={token}&next={PUBLIC_INDEX_DEFAULT_PATH}", follow_redirects=False
    )
    db.refresh(user)
    print("verify_ok", verify_ok.status_code, verify_ok.headers.get("location"), "verified", user.email_verified)
    db.delete(user)
    db.commit()
    db.close()


if __name__ == "__main__":
    main()

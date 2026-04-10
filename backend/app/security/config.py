"""JWT and environment constants; fail fast on insecure secrets in production."""

from __future__ import annotations

import os

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "120"))
PUBLIC_JWT_SECRET = os.getenv("PUBLIC_JWT_SECRET", JWT_SECRET)
PUBLIC_SESSION_EXPIRES_MINUTES = int(os.getenv("PUBLIC_SESSION_EXPIRES_MINUTES", "10080"))  # 7 days
PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES = int(os.getenv("PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES", "30"))
PUBLIC_EMAIL_VERIFY_FLASH_EXPIRES_MINUTES = int(
    os.getenv("PUBLIC_EMAIL_VERIFY_FLASH_EXPIRES_MINUTES", "30")
)
PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES = int(os.getenv("PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES", "30"))
PUBLIC_ACCOUNT_DELETE_EXPIRES_MINUTES = int(os.getenv("PUBLIC_ACCOUNT_DELETE_EXPIRES_MINUTES", "30"))
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
_INSECURE_SECRET_VALUES = {
    "",
    "change-this-in-production",
    "change-this-in-production-too",
    "changeme",
}


def _validate_token_secrets() -> None:
    if APP_ENV in {"development", "dev", "local", "test", "testing"}:
        return
    if JWT_SECRET in _INSECURE_SECRET_VALUES:
        raise RuntimeError("JWT_SECRET is missing or insecure for non-development environment.")
    if PUBLIC_JWT_SECRET in _INSECURE_SECRET_VALUES:
        raise RuntimeError("PUBLIC_JWT_SECRET is missing or insecure for non-development environment.")
    if JWT_SECRET == PUBLIC_JWT_SECRET:
        raise RuntimeError("JWT_SECRET and PUBLIC_JWT_SECRET must be different in non-development environment.")


_validate_token_secrets()

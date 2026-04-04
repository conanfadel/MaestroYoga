import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models
from .database import get_db

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "120"))
PUBLIC_JWT_SECRET = os.getenv("PUBLIC_JWT_SECRET", JWT_SECRET)
PUBLIC_SESSION_EXPIRES_MINUTES = int(os.getenv("PUBLIC_SESSION_EXPIRES_MINUTES", "10080"))  # 7 days
PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES = int(os.getenv("PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES", "30"))
PUBLIC_EMAIL_VERIFY_FLASH_EXPIRES_MINUTES = int(os.getenv("PUBLIC_EMAIL_VERIFY_FLASH_EXPIRES_MINUTES", "30"))
PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES = int(os.getenv("PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES", "30"))
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
http_bearer_optional = HTTPBearer(auto_error=False)


def get_user_from_token_string(token: str, db: Session) -> models.User:
    return _user_from_token(token, db)


def _user_from_token(token: str, db: Session) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise unauthorized
    user = db.get(models.User, user_id)
    if not user or not user.is_active:
        raise unauthorized
    return user


def get_current_user_cookie_or_bearer(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_optional),
    db: Session = Depends(get_db),
) -> models.User:
    token = creds.credentials if creds else None
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_user_from_token_string(token, db)


def require_roles_cookie_or_bearer(*roles: str):
    def checker(user: models.User = Depends(get_current_user_cookie_or_bearer)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return hmac.compare_digest(digest, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_public_access_token(public_user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=PUBLIC_SESSION_EXPIRES_MINUTES)
    payload = {"sub": str(public_user_id), "purpose": "public_session", "exp": expire}
    return jwt.encode(payload, PUBLIC_JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_public_email_verification_token(public_user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES)
    payload = {
        "sub": str(public_user_id),
        "email": email.lower(),
        "purpose": "public_email_verification",
        "exp": expire,
    }
    return jwt.encode(payload, PUBLIC_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_public_email_verification_token(token: str) -> dict:
    invalid = HTTPException(status_code=400, detail="Invalid or expired verification link")
    try:
        payload = jwt.decode(token, PUBLIC_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != "public_email_verification":
        raise invalid
    return payload


def create_public_email_verify_flash_token(public_user_id: int, email: str) -> str:
    """Short-lived token appended after verify-email so verify-pending can show success even if Set-Cookie is dropped (e.g. in-app browsers)."""
    mins = max(5, PUBLIC_EMAIL_VERIFY_FLASH_EXPIRES_MINUTES)
    expire = datetime.now(timezone.utc) + timedelta(minutes=mins)
    payload = {
        "sub": str(public_user_id),
        "email": email.lower(),
        "purpose": "public_email_verify_flash",
        "exp": expire,
    }
    return jwt.encode(payload, PUBLIC_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_public_email_verify_flash_token(token: str) -> dict:
    invalid = HTTPException(status_code=400, detail="Invalid or expired verify confirmation")
    try:
        payload = jwt.decode(token, PUBLIC_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != "public_email_verify_flash":
        raise invalid
    return payload


def create_public_password_reset_token(public_user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES)
    payload = {
        "sub": str(public_user_id),
        "email": email.lower(),
        "purpose": "public_password_reset",
        "exp": expire,
    }
    return jwt.encode(payload, PUBLIC_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_public_password_reset_token(token: str) -> dict:
    invalid = HTTPException(status_code=400, detail="Invalid or expired reset link")
    try:
        payload = jwt.decode(token, PUBLIC_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != "public_password_reset":
        raise invalid
    return payload


def get_public_user_from_token_string(token: str, db: Session) -> models.PublicUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired public session",
    )
    try:
        payload = jwt.decode(token, PUBLIC_JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "public_session":
            raise unauthorized
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise unauthorized
    user = db.get(models.PublicUser, user_id)
    if not user or not user.is_active or user.is_deleted:
        raise unauthorized
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    return get_user_from_token_string(token, db)


def require_roles(*roles: str):
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker

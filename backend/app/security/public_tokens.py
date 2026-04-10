"""Public-user JWTs: session, email verify, password reset, account delete."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .. import models
from .config import (
    JWT_ALGORITHM,
    PUBLIC_ACCOUNT_DELETE_EXPIRES_MINUTES,
    PUBLIC_EMAIL_VERIFY_EXPIRES_MINUTES,
    PUBLIC_EMAIL_VERIFY_FLASH_EXPIRES_MINUTES,
    PUBLIC_JWT_SECRET,
    PUBLIC_PASSWORD_RESET_EXPIRES_MINUTES,
    PUBLIC_SESSION_EXPIRES_MINUTES,
)


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


def create_public_account_delete_token(public_user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=PUBLIC_ACCOUNT_DELETE_EXPIRES_MINUTES)
    payload = {
        "sub": str(public_user_id),
        "email": email.lower(),
        "purpose": "public_account_delete",
        "exp": expire,
    }
    return jwt.encode(payload, PUBLIC_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_public_account_delete_token(token: str) -> dict:
    invalid = HTTPException(status_code=400, detail="Invalid or expired account-delete link")
    try:
        payload = jwt.decode(token, PUBLIC_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != "public_account_delete":
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

"""Staff JWT: access/refresh tokens (DB-backed refresh rotation) and user resolution."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import and_
from sqlalchemy.orm import Session

from .. import models
from ..time_utils import utcnow_naive
from .config import JWT_ALGORITHM, JWT_EXPIRES_MINUTES, JWT_SECRET

JWT_REFRESH_EXPIRES_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRES_MINUTES", "43200"))


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
        if payload.get("type") not in (None, "access"):
            raise unauthorized
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise unauthorized
    user = db.get(models.User, user_id)
    if not user or not user.is_active:
        raise unauthorized
    return user


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def issue_staff_refresh_token(db: Session, user_id: int) -> str:
    """Create a persisted refresh session and return a JWT containing its jti."""
    jti = str(uuid.uuid4())
    expires_at_utc = datetime.now(timezone.utc) + timedelta(minutes=JWT_REFRESH_EXPIRES_MINUTES)
    expires_at_naive = expires_at_utc.replace(tzinfo=None)
    row = models.StaffRefreshToken(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at_naive,
    )
    db.add(row)
    db.flush()
    payload = {"sub": str(user_id), "exp": expires_at_utc, "type": "refresh", "jti": jti}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def validate_staff_refresh_token(db: Session, token: str) -> tuple[models.User, str]:
    """Validate JWT + DB row; return (user, jti)."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise unauthorized
        jti = payload.get("jti")
        if not jti or not isinstance(jti, str):
            raise unauthorized
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise unauthorized

    row = db.query(models.StaffRefreshToken).filter(models.StaffRefreshToken.jti == jti).first()
    if not row or row.revoked_at is not None:
        raise unauthorized
    if row.user_id != user_id:
        raise unauthorized
    if row.expires_at < utcnow_naive():
        raise unauthorized

    user = db.get(models.User, user_id)
    if not user or not user.is_active:
        raise unauthorized
    return user, jti


def revoke_staff_refresh_token(db: Session, jti: str) -> None:
    row = db.query(models.StaffRefreshToken).filter(models.StaffRefreshToken.jti == jti).first()
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = utcnow_naive()


def revoke_all_staff_refresh_tokens_for_user(db: Session, user_id: int) -> None:
    now = utcnow_naive()
    db.query(models.StaffRefreshToken).filter(
        and_(
            models.StaffRefreshToken.user_id == user_id,
            models.StaffRefreshToken.revoked_at.is_(None),
        )
    ).update({"revoked_at": now}, synchronize_session=False)

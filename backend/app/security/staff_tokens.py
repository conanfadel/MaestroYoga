"""Staff JWT: access/refresh tokens and user resolution."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .. import models
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


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_REFRESH_EXPIRES_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_from_refresh_token_string(token: str, db: Session) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise unauthorized
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise unauthorized
    user = db.get(models.User, user_id)
    if not user or not user.is_active:
        raise unauthorized
    return user

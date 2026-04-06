"""واجهة REST لتسجيل أجهزة FCM وتفضيلات الإشعارات (حساب الجمهور)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .push_service import register_or_refresh_device, unregister_device
from .security import get_public_user_from_token_string

push_router = APIRouter(tags=["push"])
bearer_optional = HTTPBearer(auto_error=False)


def _public_user_dep(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_optional),
    db: Session = Depends(get_db),
) -> models.PublicUser:
    token = (creds.credentials if creds else None) or request.cookies.get("public_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return get_public_user_from_token_string(token, db)


class FcmRegisterIn(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=512)
    platform: str = Field(default="android", description="android or ios")


class FcmUnregisterIn(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=512)


class PushPrefsOut(BaseModel):
    push_enabled: bool
    push_reminders: bool
    push_bookings: bool
    push_waitlist: bool
    push_marketing: bool


class PushPrefsPatch(BaseModel):
    push_enabled: bool | None = None
    push_reminders: bool | None = None
    push_bookings: bool | None = None
    push_waitlist: bool | None = None
    push_marketing: bool | None = None


@push_router.post("/push/register")
def push_register(
    payload: FcmRegisterIn,
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    try:
        register_or_refresh_device(db, user.id, payload.fcm_token, payload.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@push_router.post("/push/unregister")
def push_unregister(
    payload: FcmUnregisterIn,
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    n = unregister_device(db, user.id, payload.fcm_token)
    return {"status": "ok", "removed": n}


@push_router.get("/push/preferences", response_model=PushPrefsOut)
def push_preferences_get(
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    return PushPrefsOut(
        push_enabled=bool(user.push_enabled),
        push_reminders=bool(user.push_reminders),
        push_bookings=bool(user.push_bookings),
        push_waitlist=bool(user.push_waitlist),
        push_marketing=bool(user.push_marketing),
    )


@push_router.patch("/push/preferences", response_model=PushPrefsOut)
def push_preferences_patch(
    payload: PushPrefsPatch,
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    data = payload.model_dump(exclude_unset=True)
    for key, val in data.items():
        setattr(user, key, val)
    db.commit()
    db.refresh(user)
    return PushPrefsOut(
        push_enabled=bool(user.push_enabled),
        push_reminders=bool(user.push_reminders),
        push_bookings=bool(user.push_bookings),
        push_waitlist=bool(user.push_waitlist),
        push_marketing=bool(user.push_marketing),
    )

from urllib.parse import urlencode

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .mailer import queue_email_verification_email
from .security import (
    create_public_email_verification_token,
    create_public_password_reset_token,
    decode_public_email_verify_flash_token,
)
from .web_shared import _public_base, _sanitize_next_url, PUBLIC_INDEX_DEFAULT_PATH


def public_user_from_verify_flash_token(db: Session, vk: str) -> models.PublicUser | None:
    vk_value = (vk or "").strip()
    if not vk_value:
        return None
    try:
        payload = decode_public_email_verify_flash_token(vk_value)
    except HTTPException:
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.is_deleted or not user.is_active:
        return None
    if user.email.lower() != email:
        return None
    if not user.email_verified:
        return None
    return user


def build_verify_url(request: Request, user: models.PublicUser, next_url: str = PUBLIC_INDEX_DEFAULT_PATH) -> str:
    token = create_public_email_verification_token(user.id, user.email)
    safe_next = _sanitize_next_url(next_url)
    query = urlencode({"token": token, "next": safe_next})
    return f"{_public_base(request)}/public/verify-email?{query}"


def build_reset_url(request: Request, user: models.PublicUser) -> str:
    token = create_public_password_reset_token(user.id, user.email)
    query = urlencode({"token": token})
    return f"{_public_base(request)}/public/reset-password?{query}"


def queue_verify_email_for_user(
    request: Request, user: models.PublicUser, next_url: str = PUBLIC_INDEX_DEFAULT_PATH
) -> tuple[bool, str]:
    verify_url = build_verify_url(request, user, next_url=next_url)
    return queue_email_verification_email(user.email, verify_url, full_name=user.full_name)

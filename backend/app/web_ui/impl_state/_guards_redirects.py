"""Public/admin session gates, IP block checks, and HTML redirects."""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ... import models
from ...request_ip import get_client_ip
from ...role_definitions import CENTER_ADMIN_LOGIN_ROLES
from ...security import get_public_user_from_token_string, get_user_from_token_string
from ...time_utils import utcnow_naive
from ...web_shared import PUBLIC_INDEX_DEFAULT_PATH, _sanitize_next_url, _url_with_params
from ._constants import (
    ADMIN_MSG_PUBLIC_USER_NOT_FOUND,
    ADMIN_MSG_SECURITY_OWNER_ONLY,
    ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN,
    ALLOWED_ADMIN_RETURN_SECTIONS,
    PUBLIC_COOKIE_NAME,
)


def _current_public_user(request: Request, db: Session) -> models.PublicUser | None:
    token = request.cookies.get(PUBLIC_COOKIE_NAME)
    if not token:
        return None
    try:
        return get_public_user_from_token_string(token, db)
    except HTTPException:
        return None


def _request_key(request: Request, prefix: str, identity: str = "") -> str:
    client_ip = get_client_ip(request)
    scope = identity.strip().lower() if identity else client_ip
    return f"{prefix}:{scope}"


def _active_block_for_ip(db: Session, ip: str) -> models.BlockedIP | None:
    now = utcnow_naive()
    return (
        db.query(models.BlockedIP)
        .filter(
            models.BlockedIP.ip == ip,
            models.BlockedIP.is_active.is_(True),
            or_(models.BlockedIP.blocked_until.is_(None), models.BlockedIP.blocked_until > now),
        )
        .order_by(models.BlockedIP.created_at.desc())
        .first()
    )


def _is_ip_blocked(db: Session, request: Request) -> bool:
    return _active_block_for_ip(db, get_client_ip(request)) is not None


def _sanitize_admin_return_section(raw: str | None) -> str | None:
    s = (raw or "").strip()
    return s if s in ALLOWED_ADMIN_RETURN_SECTIONS else None


def _admin_redirect(
    msg: str | None = None,
    scroll_y: str | None = None,
    return_section: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {}
    if msg:
        params["msg"] = msg
    if scroll_y:
        try:
            parsed = int(float(scroll_y))
            if parsed >= 0:
                params["scroll_y"] = str(parsed)
        except (TypeError, ValueError):
            pass
    url = "/admin"
    if params:
        url = f"{url}?{urlencode(params)}"
    sec = _sanitize_admin_return_section(return_section)
    if sec:
        url = f"{url}#{sec}"
    return RedirectResponse(url=url, status_code=303)


def _parse_optional_date_str(value: str | None) -> date | None:
    s = (value or "").strip()[:10]
    if len(s) < 8:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _trainer_forbidden_redirect(return_section: str | None = None) -> RedirectResponse:
    return _admin_redirect(
        ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN,
        scroll_y=None,
        return_section=return_section,
    )


def _security_owner_forbidden_redirect(return_section: str | None = None) -> RedirectResponse:
    return _admin_redirect(
        ADMIN_MSG_SECURITY_OWNER_ONLY,
        scroll_y=None,
        return_section=return_section,
    )


def _admin_login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/login", status_code=303)


def _require_admin_user_or_redirect(
    request: Request, db: Session
) -> tuple[models.User | None, RedirectResponse | None]:
    user = _admin_user_from_request(request, db)
    if not user:
        return None, _admin_login_redirect()
    return user, None


def _public_login_redirect(next_url: str = PUBLIC_INDEX_DEFAULT_PATH, msg: str | None = None) -> RedirectResponse:
    safe_next = _sanitize_next_url(next_url)
    return RedirectResponse(url=_url_with_params("/public/login", next=safe_next, msg=msg), status_code=303)


def _admin_user_from_request(request: Request, db: Session) -> models.User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        user = get_user_from_token_string(token, db)
    except HTTPException:
        return None
    if user.role not in CENTER_ADMIN_LOGIN_ROLES:
        return None
    return user


def _get_public_user_or_redirect(
    db: Session,
    center_id: int,
    public_user_id: int,
    scroll_y: str,
    *,
    allow_deleted: bool = False,
    return_section: str | None = None,
) -> tuple[models.PublicUser | None, RedirectResponse | None]:
    row = (
        db.query(models.PublicUser)
        .filter(
            models.PublicUser.id == public_user_id,
            db.query(models.Client.id)
            .filter(
                models.Client.center_id == center_id,
                func.lower(models.Client.email) == func.lower(models.PublicUser.email),
            )
            .exists(),
        )
        .first()
    )
    if not row:
        return None, _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)
    if not allow_deleted and row.is_deleted:
        return None, _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)
    return row, None

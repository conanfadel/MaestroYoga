import csv
import io
import json
from datetime import datetime, timedelta
import os
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from . import models
from .booking_utils import ACTIVE_BOOKING_STATUSES, spots_available
from .bootstrap import ensure_demo_data
from .database import get_db
from .mailer import (
    queue_email_verification_email,
    queue_password_reset_email,
    validate_mailer_settings,
)
from .payments import StripePaymentProvider, get_payment_provider
from .rate_limiter import rate_limiter
from .request_ip import get_client_ip
from .security_audit import log_security_event
from .security import (
    create_access_token,
    create_public_access_token,
    create_public_email_verification_token,
    create_public_password_reset_token,
    decode_public_email_verification_token,
    decode_public_password_reset_token,
    get_public_user_from_token_string,
    get_user_from_token_string,
    hash_password,
    require_roles_cookie_or_bearer,
    verify_password,
)
from .tenant_utils import require_user_center_id
from .time_utils import utcnow_naive
from .web_shared import (
    _cookie_secure_flag,
    _fmt_dt,
    _is_email_verification_required,
    _is_truthy_env,
    _normalize_phone_with_country,
    _plan_duration_days,
    _public_base,
    _sanitize_next_url,
    _url_with_params,
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(tags=["web"])
PUBLIC_COOKIE_NAME = "public_access_token"
MAX_LOCKOUT_SECONDS = int(os.getenv("RATE_LIMIT_MAX_LOCKOUT_SECONDS", "900"))
GA4_MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID", "").strip()


def _current_public_user(request: Request, db: Session) -> models.PublicUser | None:
    token = request.cookies.get(PUBLIC_COOKIE_NAME)
    if not token:
        return None
    try:
        return get_public_user_from_token_string(token, db)
    except HTTPException:
        return None


def _build_verify_url(request: Request, user: models.PublicUser, next_url: str = "/index?center_id=1") -> str:
    token = create_public_email_verification_token(user.id, user.email)
    safe_next = _sanitize_next_url(next_url)
    query = urlencode({"token": token, "next": safe_next})
    return f"{_public_base(request)}/public/verify-email?{query}"


def _build_reset_url(request: Request, user: models.PublicUser) -> str:
    token = create_public_password_reset_token(user.id, user.email)
    query = urlencode({"token": token})
    return f"{_public_base(request)}/public/reset-password?{query}"


def _request_key(request: Request, prefix: str, identity: str = "") -> str:
    client_ip = get_client_ip(request)
    scope = identity.strip().lower() if identity else client_ip
    return f"{prefix}:{scope}"


def _client_ip(request: Request) -> str:
    return get_client_ip(request)


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
    return _active_block_for_ip(db, _client_ip(request)) is not None


def _admin_redirect(msg: str | None = None, scroll_y: str | None = None) -> RedirectResponse:
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
    return RedirectResponse(url=url, status_code=303)


def _public_login_redirect(next_url: str = "/index?center_id=1", msg: str | None = None) -> RedirectResponse:
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
    if user.role not in ("center_owner", "center_staff", "trainer"):
        return None
    return user


def _analytics_context(page_name: str, **extra: str) -> dict:
    data = {
        "ga4_measurement_id": GA4_MEASUREMENT_ID,
        "analytics_enabled": bool(GA4_MEASUREMENT_ID),
        "analytics_page_name": page_name,
    }
    data.update(extra)
    return data


def _queue_verify_email_for_user(request: Request, user: models.PublicUser, next_url: str = "/index?center_id=1") -> tuple[bool, str]:
    verify_url = _build_verify_url(request, user, next_url=next_url)
    return queue_email_verification_email(user.email, verify_url, full_name=user.full_name)


def _soft_delete_public_user(row: models.PublicUser) -> tuple[str, str]:
    original_email = row.email
    original_phone = row.phone or ""
    tombstone = f"deleted+{row.id}+{int(utcnow_naive().timestamp())}@maestroyoga.local"
    row.email = tombstone
    row.phone = None
    row.is_active = False
    row.email_verified = False
    row.is_deleted = True
    row.deleted_at = utcnow_naive()
    return original_email, original_phone


@router.get("/index", response_class=HTMLResponse)
def public_index(
    request: Request,
    center_id: int = 1,
    payment: str | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
):
    public_user = _current_public_user(request, db)
    center = db.get(models.Center, center_id)
    if not center:
        # Keep web pages usable even on a fresh DB.
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
        if not center:
            center = db.query(models.Center).order_by(models.Center.id.asc()).first()
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == center_id)
        .order_by(models.YogaSession.starts_at.asc())
        .all()
    )
    room_ids = sorted({s.room_id for s in sessions if s.room_id is not None})
    rooms_by_id = {}
    if room_ids:
        rooms_by_id = {
            r.id: r
            for r in db.query(models.Room).filter(models.Room.center_id == center_id, models.Room.id.in_(room_ids)).all()
        }
    rows = []
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "spots_available": spots_available(db, s),
            }
        )

    plans = (
        db.query(models.SubscriptionPlan)
        .filter(
            models.SubscriptionPlan.center_id == center_id,
            models.SubscriptionPlan.is_active.is_(True),
        )
        .order_by(models.SubscriptionPlan.price.asc())
        .all()
    )
    faq_items = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == center_id, models.FAQItem.is_active.is_(True))
        .order_by(models.FAQItem.sort_order.asc(), models.FAQItem.created_at.asc())
        .all()
    )
    plan_labels = {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "center": center,
            "center_id": center_id,
            "sessions": rows,
            "plans": [
                {
                    "id": p.id,
                    "name": p.name,
                    "plan_type": p.plan_type,
                    "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
                    "duration_days": _plan_duration_days(p.plan_type),
                    "price": p.price,
                    "session_limit": p.session_limit,
                }
                for p in plans
            ],
            "payment": payment,
            "msg": msg,
            "public_user": public_user,
            "faq_items": faq_items,
            **_analytics_context("index", center_id=str(center_id)),
        },
    )


@router.post("/public/book")
def public_book(
    request: Request,
    center_id: int = Form(...),
    session_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    yoga_session = db.get(models.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != center_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if spots_available(db, yoga_session) <= 0:
        return RedirectResponse(
            url=f"/index?center_id={center_id}&msg=full",
            status_code=303,
        )

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    duplicate = (
        db.query(models.Booking)
        .filter(
            models.Booking.session_id == session_id,
            models.Booking.client_id == client.id,
            models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .first()
    )
    if duplicate:
        return RedirectResponse(
            url=f"/index?center_id={center_id}&msg=duplicate",
            status_code=303,
        )

    booking = models.Booking(
        center_id=center_id,
        session_id=session_id,
        client_id=client.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()

    amount = float(yoga_session.price_drop_in)
    payment_row = models.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=booking.id,
        amount=amount,
        currency="SAR",
        payment_method="public_checkout",
        status="pending",
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)

    provider = get_payment_provider()
    base = _public_base(request)

    if isinstance(provider, StripePaymentProvider):
        try:
            provider_result = provider.create_checkout_session(
                amount=amount,
                currency="sar",
                metadata={
                    "payment_id": str(payment_row.id),
                    "booking_id": str(booking.id),
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled",
            )
        except Exception as exc:
            booking.status = "cancelled"
            payment_row.status = "failed"
            db.commit()
            log_security_event(
                "public_book",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id, "session_id": session_id},
            )
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_error",
                status_code=303,
            )

        payment_row.provider_ref = provider_result.provider_ref
        db.commit()
        checkout_url = provider_result.checkout_url or ""
        if not checkout_url:
            booking.status = "cancelled"
            payment_row.status = "failed"
            db.commit()
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_no_url",
                status_code=303,
            )
        return RedirectResponse(url=checkout_url, status_code=303)

    provider_result = provider.charge(
        amount=amount,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client.id, "booking_id": booking.id},
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    booking.status = "confirmed"
    db.commit()

    return RedirectResponse(
        url=f"/index?center_id={center_id}&msg=paid_mock&booking_id={booking.id}",
        status_code=303,
    )


@router.get("/public/register", response_class=HTMLResponse)
def public_register_page(request: Request):
    return templates.TemplateResponse(request, "public_register.html", _analytics_context("public_register"))


@router.post("/public/register")
def public_register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    country_code: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    email_normalized = email.lower().strip()
    full_name_normalized = full_name.strip()
    phone_normalized = _normalize_phone_with_country(country_code, phone)
    if (
        not full_name_normalized
        or not email_normalized
        or not password.strip()
        or not phone.strip()
        or not country_code.strip()
    ):
        return RedirectResponse(url="/public/register?msg=required_fields", status_code=303)
    if phone_normalized is None:
        return RedirectResponse(url="/public/register?msg=invalid_phone", status_code=303)
    register_key = _request_key(request, "public_register", email_normalized)
    if not rate_limiter.allow(
        register_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_register", request, "rate_limited", email=email_normalized)
        return RedirectResponse(url="/public/register?msg=rate_limited", status_code=303)
    exists = db.query(models.PublicUser).filter(models.PublicUser.email == email_normalized).first()
    if exists and not exists.is_deleted:
        log_security_event("public_register", request, "already_exists", email=email_normalized)
        return _public_login_redirect(msg="account_exists")
    phone_exists = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.phone == phone_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    if phone_exists:
        log_security_event("public_register", request, "phone_already_exists", email=email_normalized)
        return RedirectResponse(url="/public/register?msg=phone_exists", status_code=303)
    if len(password) < 8:
        log_security_event("public_register", request, "weak_password", email=email_normalized)
        return RedirectResponse(url="/public/register?msg=weak_password", status_code=303)

    if exists and exists.is_deleted:
        user = exists
        user.full_name = full_name_normalized
        user.email = email_normalized
        user.phone = phone_normalized
        user.password_hash = hash_password(password)
        user.email_verified = not _is_email_verification_required()
        user.verification_sent_at = utcnow_naive()
        user.is_active = True
        user.is_deleted = False
        user.deleted_at = None
        status_label = "restored"
    else:
        user = models.PublicUser(
            full_name=full_name_normalized,
            email=email_normalized,
            phone=phone_normalized,
            password_hash=hash_password(password),
            email_verified=not _is_email_verification_required(),
            verification_sent_at=utcnow_naive(),
            is_active=True,
            is_deleted=False,
        )
        db.add(user)
        status_label = "created"
    db.commit()
    db.refresh(user)

    queued, mail_info = (True, "verification_bypassed")
    if _is_email_verification_required():
        queued, mail_info = _queue_verify_email_for_user(request, user)
    if not queued:
        log_security_event(
            "public_register",
            request,
            "mail_failed",
            email=user.email,
            details={"mail_error": mail_info[:200], "state": status_label},
        )
    else:
        log_security_event(
            "public_register",
            request,
            "success",
            email=user.email,
            details={"mail_status": "queued", "state": status_label},
        )
    token = create_public_access_token(user.id)
    if _is_email_verification_required():
        next_msg = "registered" if queued else "mail_failed"
        response = RedirectResponse(url=f"/public/verify-pending?msg={next_msg}", status_code=303)
    else:
        response = RedirectResponse(url="/index?center_id=1&msg=registered_no_verify", status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/public/login", response_class=HTMLResponse)
def public_login_page(request: Request, next: str = "/index?center_id=1"):
    return templates.TemplateResponse(request, "public_login.html", {"next": next, **_analytics_context("public_login")})


@router.post("/public/login")
def public_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/index?center_id=1"),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    email_normalized = email.lower().strip()
    login_key = _request_key(request, "public_login", email_normalized)
    if not rate_limiter.allow(
        login_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_login", request, "rate_limited", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="rate_limited")
    user = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.email == email_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        log_security_event("public_login", request, "invalid_credentials", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="invalid_credentials")
    if not user.is_active:
        log_security_event("public_login", request, "inactive", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="inactive")

    token = create_public_access_token(user.id)
    if _is_email_verification_required() and not user.email_verified:
        response = RedirectResponse(url=_url_with_params("/public/verify-pending", next=safe_next), status_code=303)
    else:
        response = RedirectResponse(url=safe_next, status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    log_security_event(
        "public_login",
        request,
        "success",
        email=user.email,
        details={"email_verified": user.email_verified},
    )
    return response


@router.get("/public/logout")
def public_logout():
    # Request object is not required for logout, so this event is not logged here.
    response = RedirectResponse(url="/index?center_id=1&msg=logged_out", status_code=303)
    response.delete_cookie(PUBLIC_COOKIE_NAME)
    return response


@router.get("/public/verify-pending", response_class=HTMLResponse)
def public_verify_pending(request: Request, next: str = "/index?center_id=1", db: Session = Depends(get_db)):
    safe_next = _sanitize_next_url(next)
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    if not _is_email_verification_required():
        return RedirectResponse(url=safe_next, status_code=303)
    if user.email_verified:
        return RedirectResponse(url=safe_next, status_code=303)
    show_dev_verify_link = _is_truthy_env(os.getenv("SHOW_DEV_VERIFY_LINK"))
    dev_verify_url = _build_verify_url(request, user, next_url=safe_next) if show_dev_verify_link else ""
    return templates.TemplateResponse(
        request,
        "public_verify_pending.html",
        {
            "next": safe_next,
            "user": user,
            "show_dev_verify_link": show_dev_verify_link,
            "dev_verify_url": dev_verify_url,
            **_analytics_context("public_verify_pending"),
        },
    )


@router.post("/public/resend-verification")
def public_resend_verification(
    request: Request,
    next: str = Form("/index?center_id=1"),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    resend_key = _request_key(request, "public_resend_verify")
    if not rate_limiter.allow(
        resend_key,
        limit=6,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_resend_verification", request, "rate_limited")
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="rate_limited", next=safe_next),
            status_code=303,
        )
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    now = utcnow_naive()
    if user.verification_sent_at and (now - user.verification_sent_at).total_seconds() < 60:
        log_security_event("public_resend_verification", request, "too_soon", email=user.email)
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="resend_too_soon", next=safe_next),
            status_code=303,
        )
    user.verification_sent_at = now
    db.commit()
    queued, mail_info = _queue_verify_email_for_user(request, user, next_url=safe_next)
    if not queued:
        log_security_event(
            "public_resend_verification",
            request,
            "mail_failed",
            email=user.email,
            details={"mail_error": mail_info[:200]},
        )
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="mail_failed", next=safe_next),
            status_code=303,
        )
    log_security_event(
        "public_resend_verification",
        request,
        "success",
        email=user.email,
        details={"mail_status": "queued"},
    )
    return RedirectResponse(
        url=_url_with_params("/public/verify-pending", msg="resent", next=safe_next),
        status_code=303,
    )


@router.get("/public/verify-email")
def public_verify_email(
    request: Request,
    token: str = "",
    next: str = "/index?center_id=1",
    db: Session = Depends(get_db),
):
    token_value = token.strip().strip("<>").strip('"').strip("'")
    safe_next = _sanitize_next_url(next)
    if not token_value:
        return RedirectResponse(url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next), status_code=303)
    try:
        payload = decode_public_email_verification_token(token_value)
    except HTTPException:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="expired_link", next=safe_next),
            status_code=303,
        )
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next),
            status_code=303,
        )
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next),
            status_code=303,
        )
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    session_token = create_public_access_token(user.id)
    separator = "&" if "?" in safe_next else "?"
    response = RedirectResponse(url=f"{safe_next}{separator}msg=email_verified", status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    # No Request object in this signature for IP/user-agent audit.
    return response


@router.get("/public/forgot-password", response_class=HTMLResponse)
def public_forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "public_forgot_password.html", _analytics_context("public_forgot_password"))


@router.post("/public/forgot-password")
def public_forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    email_normalized = email.lower().strip()
    forgot_key = _request_key(request, "public_forgot_password", email_normalized)
    if not rate_limiter.allow(
        forgot_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_forgot_password", request, "rate_limited", email=email_normalized)
        return RedirectResponse(url="/public/forgot-password?msg=rate_limited", status_code=303)

    user = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.email == email_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    mail_sent = False
    if user and user.is_active:
        reset_url = _build_reset_url(request, user)
        mail_sent, mail_info = queue_password_reset_email(user.email, reset_url, full_name=user.full_name)
        if not mail_sent:
            log_security_event(
                "public_forgot_password",
                request,
                "mail_failed",
                email=email_normalized,
                details={"mail_error": mail_info[:200]},
            )
    log_security_event("public_forgot_password", request, "accepted", email=email_normalized)
    # Keep response neutral, but surface delivery issue when sending fails for an existing account.
    if user and user.is_active and not mail_sent:
        return RedirectResponse(url="/public/forgot-password?msg=mail_failed", status_code=303)
    return RedirectResponse(url="/public/forgot-password?msg=sent", status_code=303)


@router.get("/public/reset-password", response_class=HTMLResponse)
def public_reset_password_page(request: Request, token: str):
    return templates.TemplateResponse(
        request,
        "public_reset_password.html",
        {"token": token, **_analytics_context("public_reset_password")},
    )


@router.post("/public/reset-password")
def public_reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    reset_key = _request_key(request, "public_reset_password")
    if not rate_limiter.allow(
        reset_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_reset_password", request, "rate_limited")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="rate_limited"),
            status_code=303,
        )
    if len(password) < 8:
        log_security_event("public_reset_password", request, "weak_password")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="weak_password"),
            status_code=303,
        )
    if password != confirm_password:
        log_security_event("public_reset_password", request, "password_mismatch")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="password_mismatch"),
            status_code=303,
        )

    try:
        payload = decode_public_password_reset_token(token)
        user_id = int(payload.get("sub"))
    except (HTTPException, TypeError, ValueError):
        log_security_event("public_reset_password", request, "invalid_token")
        return _public_login_redirect(msg="invalid_reset_link")
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        log_security_event("public_reset_password", request, "invalid_token")
        return _public_login_redirect(msg="invalid_reset_link")

    user.password_hash = hash_password(password)
    user.is_active = True
    db.commit()
    log_security_event("public_reset_password", request, "success", email=user.email)
    return _public_login_redirect(msg="password_reset_success")


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    # Ensure there is at least one admin-capable user in fresh installs.
    ensure_demo_data(db)
    return templates.TemplateResponse(request, "admin_login.html", {})


@router.post("/admin/login")
def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/admin/login?error=1", status_code=303)
    if user.role not in ("center_owner", "center_staff", "trainer"):
        return RedirectResponse(url="/admin/login?error=role", status_code=303)

    token = create_access_token(user.id)
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 12,
    )
    return response


@router.get("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    msg: str | None = None,
    room_sort: str = "name",
    public_user_q: str = "",
    public_user_status: str = "active",
    public_user_verified: str = "all",
    audit_event_type: str = "",
    audit_status: str = "",
    audit_email: str = "",
    audit_ip: str = "",
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    room_sort_key = (room_sort or "name").strip().lower()
    room_ordering = {
        "name": (models.Room.name.asc(), models.Room.id.asc()),
        "newest": (models.Room.id.desc(),),
        "capacity_desc": (models.Room.capacity.desc(), models.Room.name.asc(), models.Room.id.asc()),
        "capacity_asc": (models.Room.capacity.asc(), models.Room.name.asc(), models.Room.id.asc()),
    }
    if room_sort_key in {"sessions_desc", "sessions_asc"}:
        session_count_order = (
            func.count(models.YogaSession.id).desc()
            if room_sort_key == "sessions_desc"
            else func.count(models.YogaSession.id).asc()
        )
        rooms = (
            db.query(models.Room)
            .outerjoin(
                models.YogaSession,
                and_(
                    models.YogaSession.room_id == models.Room.id,
                    models.YogaSession.center_id == cid,
                ),
            )
            .filter(models.Room.center_id == cid)
            .group_by(models.Room.id)
            .order_by(session_count_order, models.Room.name.asc(), models.Room.id.asc())
            .all()
        )
    else:
        room_order_by = room_ordering.get(room_sort_key, room_ordering["name"])
        rooms = (
            db.query(models.Room)
            .filter(models.Room.center_id == cid)
            .order_by(*room_order_by)
            .all()
        )
    plans = (
        db.query(models.SubscriptionPlan)
        .filter(models.SubscriptionPlan.center_id == cid)
        .order_by(models.SubscriptionPlan.price.asc())
        .all()
    )
    sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid)
        .order_by(models.YogaSession.starts_at.desc())
        .all()
    )
    faqs = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == cid)
        .order_by(models.FAQItem.sort_order.asc(), models.FAQItem.created_at.asc())
        .all()
    )
    public_users_query = db.query(models.PublicUser)
    q = public_user_q.strip()
    if q:
        public_users_query = public_users_query.filter(
            or_(
                models.PublicUser.full_name.ilike(f"%{q}%"),
                models.PublicUser.email.ilike(f"%{q}%"),
                models.PublicUser.phone.ilike(f"%{q}%"),
            )
        )
    status_key = public_user_status.strip().lower() or "active"
    if status_key == "deleted":
        public_users_query = public_users_query.filter(models.PublicUser.is_deleted.is_(True))
    elif status_key == "inactive":
        public_users_query = public_users_query.filter(
            models.PublicUser.is_deleted.is_(False), models.PublicUser.is_active.is_(False)
        )
    else:
        public_users_query = public_users_query.filter(
            models.PublicUser.is_deleted.is_(False), models.PublicUser.is_active.is_(True)
        )
    verified_key = public_user_verified.strip().lower()
    if verified_key == "verified":
        public_users_query = public_users_query.filter(models.PublicUser.email_verified.is_(True))
    elif verified_key == "unverified":
        public_users_query = public_users_query.filter(models.PublicUser.email_verified.is_(False))
    public_users = public_users_query.order_by(models.PublicUser.created_at.desc()).limit(300).all()
    session_rows = []
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    rooms_by_id = {r.id: r for r in rooms}
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        session_rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "room_id": s.room_id,
                "spots_available": spots_available(db, s),
                "capacity": room.capacity if room else 0,
            }
        )
    plan_labels = {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }
    plan_rows = [
        {
            "id": p.id,
            "name": p.name,
            "plan_type": p.plan_type,
            "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
            "price": p.price,
            "session_limit": p.session_limit,
            "is_active": p.is_active,
        }
        for p in plans
    ]

    today = utcnow_naive().date()
    recent_public_cutoff = utcnow_naive() - timedelta(days=7)
    dashboard = {
        "rooms_count": len(rooms),
        "sessions_count": len(sessions),
        "bookings_count": db.query(models.Booking).filter(models.Booking.center_id == cid).count(),
        "clients_count": db.query(models.Client).filter(models.Client.center_id == cid).count(),
        "active_plans_count": (
            db.query(models.SubscriptionPlan)
            .filter(
                models.SubscriptionPlan.center_id == cid,
                models.SubscriptionPlan.is_active.is_(True),
            )
            .count()
        ),
        "active_subscriptions_count": (
            db.query(models.ClientSubscription)
            .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
            .filter(
                models.Client.center_id == cid,
                models.ClientSubscription.status == "active",
            )
            .count()
        ),
        "revenue_total": float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(models.Payment.center_id == cid, models.Payment.status == "paid")
            .scalar()
            or 0.0
        ),
        "revenue_today": float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "paid",
                func.date(models.Payment.paid_at) == today,
            )
            .scalar()
            or 0.0
        ),
        "public_users_count": db.query(models.PublicUser).filter(models.PublicUser.is_deleted.is_(False)).count(),
        "public_users_deleted_count": db.query(models.PublicUser).filter(models.PublicUser.is_deleted.is_(True)).count(),
        "public_users_new_7d": (
            db.query(models.PublicUser)
            .filter(models.PublicUser.created_at >= recent_public_cutoff, models.PublicUser.is_deleted.is_(False))
            .count()
        ),
    }
    recent_payments = (
        db.query(models.Payment)
        .filter(models.Payment.center_id == cid)
        .order_by(models.Payment.paid_at.desc())
        .limit(8)
        .all()
    )
    client_ids = [p.client_id for p in recent_payments]
    clients_by_id = {
        c.id: c
        for c in db.query(models.Client).filter(models.Client.id.in_(client_ids)).all()
    }
    status_labels = {
        "paid": "مدفوع",
        "pending": "قيد الانتظار",
        "failed": "فشل",
    }
    payment_rows = []
    for pay in recent_payments:
        client = clients_by_id.get(pay.client_id)
        payment_rows.append(
            {
                "id": pay.id,
                "client_name": client.full_name if client else f"عميل #{pay.client_id}",
                "payment_method": pay.payment_method,
                "amount": pay.amount,
                "currency": pay.currency,
                "status": pay.status,
                "status_label": status_labels.get(pay.status, pay.status),
                "paid_at_display": _fmt_dt(pay.paid_at),
            }
        )
    public_user_rows = [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone or "-",
            "is_active": u.is_active,
            "email_verified": u.email_verified,
            "is_deleted": bool(u.is_deleted),
            "deleted_at_display": _fmt_dt(u.deleted_at),
            "created_at_display": _fmt_dt(u.created_at),
        }
        for u in public_users
    ]
    faq_rows = [
        {
            "id": f.id,
            "question": f.question,
            "answer": f.answer,
            "sort_order": f.sort_order,
            "is_active": f.is_active,
        }
        for f in faqs
    ]

    audit_query = db.query(models.SecurityAuditEvent)
    if audit_event_type.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.event_type == audit_event_type.strip())
    if audit_status.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.status == audit_status.strip())
    if audit_email.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%"))
    if audit_ip.strip():
        audit_query = audit_query.filter(models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))

    security_events = audit_query.order_by(models.SecurityAuditEvent.created_at.desc()).limit(120).all()
    security_event_rows = [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "status": ev.status,
            "email": ev.email or "-",
            "ip": ev.ip or "-",
            "path": ev.path or "-",
            "details": ev.details_json or "{}",
            "created_at_display": _fmt_dt(ev.created_at),
        }
        for ev in security_events
    ]
    high_risk_since = utcnow_naive() - timedelta(hours=24)
    failed_logins_24h = (
        db.query(models.SecurityAuditEvent)
        .filter(
            models.SecurityAuditEvent.event_type == "public_login",
            models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
            models.SecurityAuditEvent.created_at >= high_risk_since,
        )
        .count()
    )
    suspicious_ips = (
        db.query(models.SecurityAuditEvent.ip, func.count(models.SecurityAuditEvent.id).label("hits"))
        .filter(
            models.SecurityAuditEvent.event_type == "public_login",
            models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
            models.SecurityAuditEvent.created_at >= high_risk_since,
        )
        .group_by(models.SecurityAuditEvent.ip)
        .having(func.count(models.SecurityAuditEvent.id) >= 5)
        .order_by(func.count(models.SecurityAuditEvent.id).desc())
        .limit(5)
        .all()
    )
    blocked_ips = (
        db.query(models.BlockedIP)
        .filter(
            models.BlockedIP.is_active.is_(True),
            or_(models.BlockedIP.blocked_until.is_(None), models.BlockedIP.blocked_until > utcnow_naive()),
        )
        .order_by(models.BlockedIP.created_at.desc())
        .limit(20)
        .all()
    )

    def _risk_level(hits: int) -> str:
        if hits >= 12:
            return "high"
        if hits >= 5:
            return "medium"
        return "low"

    security_summary = {
        "failed_logins_24h": failed_logins_24h,
        "suspicious_ips": [
            {"ip": ip or "-", "hits": int(hits), "risk_level": _risk_level(int(hits))}
            for ip, hits in suspicious_ips
        ],
        "blocked_ips": [
            {
                "ip": b.ip,
                "reason": b.reason or "-",
                "blocked_until": _fmt_dt(b.blocked_until) if b.blocked_until else "دائم",
            }
            for b in blocked_ips
        ],
    }
    block_history_events = (
        db.query(models.SecurityAuditEvent)
        .filter(models.SecurityAuditEvent.event_type.in_(["admin_ip_block", "admin_ip_unblock"]))
        .order_by(models.SecurityAuditEvent.created_at.desc())
        .limit(120)
        .all()
    )
    block_history_rows = []
    for ev in block_history_events:
        details = {}
        if ev.details_json:
            try:
                details = json.loads(ev.details_json)
            except (TypeError, ValueError):
                details = {}
        block_history_rows.append(
            {
                "id": ev.id,
                "created_at_display": _fmt_dt(ev.created_at),
                "event_type": ev.event_type,
                "status": ev.status,
                "admin_email": ev.email or "-",
                "target_ip": details.get("target_ip", "-"),
                "minutes": details.get("minutes", "-"),
                "reason": details.get("reason", "-"),
            }
        )
    security_export_url = _url_with_params(
        "/admin/security/export/csv",
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
    )

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "center": center,
            "msg": msg,
            "dashboard": dashboard,
            "rooms": rooms,
            "plans": plan_rows,
            "sessions": session_rows,
            "recent_payments": payment_rows,
            "public_users": public_user_rows,
            "faq_items": faq_rows,
            "security_events": security_event_rows,
            "security_summary": security_summary,
            "security_export_url": security_export_url,
            "block_history": block_history_rows,
            "security_filters": {
                "event_type": audit_event_type,
                "status": audit_status,
                "email": audit_email,
                "ip": audit_ip,
            },
            "public_user_filters": {
                "q": public_user_q,
                "status": status_key,
                "verified": verified_key or "all",
            },
            "room_filters": {
                "sort": (
                    room_sort_key
                    if room_sort_key in room_ordering or room_sort_key in {"sessions_desc", "sessions_asc"}
                    else "name"
                ),
            },
        },
    )


@router.get("/admin/security/export/csv")
def export_security_events_csv(
    request: Request,
    audit_event_type: str = "",
    audit_status: str = "",
    audit_email: str = "",
    audit_ip: str = "",
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)

    query = db.query(models.SecurityAuditEvent)
    if audit_event_type.strip():
        query = query.filter(models.SecurityAuditEvent.event_type == audit_event_type.strip())
    if audit_status.strip():
        query = query.filter(models.SecurityAuditEvent.status == audit_status.strip())
    if audit_email.strip():
        query = query.filter(models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%"))
    if audit_ip.strip():
        query = query.filter(models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))
    events = query.order_by(models.SecurityAuditEvent.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "event_type", "status", "email", "ip", "path", "details_json"])
    for ev in events:
        writer.writerow(
            [
                ev.id,
                ev.created_at.isoformat() if ev.created_at else "",
                ev.event_type,
                ev.status,
                ev.email or "",
                ev.ip or "",
                ev.path or "",
                ev.details_json or "",
            ]
        )
    filename = f"security_audit_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    content = output.getvalue()
    output.close()
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/admin/security/ip-block")
def admin_block_ip(
    request: Request,
    ip: str = Form(...),
    minutes: int = Form(60),
    reason: str = Form("manual_block"),
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)

    target_ip = ip.strip()
    if not target_ip:
        return RedirectResponse(url="/admin?msg=ip_block_invalid", status_code=303)
    if minutes <= 0:
        minutes = 60
    if minutes > 10080:
        minutes = 10080
    blocked_until = utcnow_naive() + timedelta(minutes=minutes)

    row = db.query(models.BlockedIP).filter(models.BlockedIP.ip == target_ip).first()
    if not row:
        row = models.BlockedIP(
            ip=target_ip,
            reason=reason[:255],
            blocked_until=blocked_until,
            is_active=True,
        )
        db.add(row)
    else:
        row.reason = reason[:255]
        row.blocked_until = blocked_until
        row.is_active = True
    db.commit()
    log_security_event(
        "admin_ip_block",
        request,
        "success",
        email=user.email,
        details={"target_ip": target_ip, "minutes": minutes, "reason": reason[:255]},
    )
    return RedirectResponse(url="/admin?msg=ip_blocked", status_code=303)


@router.post("/admin/security/ip-unblock")
def admin_unblock_ip(
    request: Request,
    ip: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    target_ip = ip.strip()
    if not target_ip:
        return RedirectResponse(url="/admin?msg=ip_block_invalid", status_code=303)
    row = db.query(models.BlockedIP).filter(models.BlockedIP.ip == target_ip).first()
    if not row:
        return RedirectResponse(url="/admin?msg=ip_unblock_not_found", status_code=303)
    row.is_active = False
    db.commit()
    log_security_event(
        "admin_ip_unblock",
        request,
        "success",
        email=user.email,
        details={"target_ip": target_ip, "reason": "manual_unblock"},
    )
    return RedirectResponse(url="/admin?msg=ip_unblocked", status_code=303)


@router.post("/admin/public-users/toggle-active")
def admin_toggle_public_user_active(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    row = db.get(models.PublicUser, public_user_id)
    if not row or row.is_deleted:
        return _admin_redirect("public_user_not_found", scroll_y)
    row.is_active = not row.is_active
    db.commit()
    return _admin_redirect("public_user_updated", scroll_y)


@router.post("/admin/public-users/toggle-verified")
def admin_toggle_public_user_verified(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    row = db.get(models.PublicUser, public_user_id)
    if not row or row.is_deleted:
        return _admin_redirect("public_user_not_found", scroll_y)
    row.email_verified = not row.email_verified
    db.commit()
    return _admin_redirect("public_user_updated", scroll_y)


@router.post("/admin/public-users/delete")
def admin_delete_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = _admin_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    row = db.get(models.PublicUser, public_user_id)
    if not row or row.is_deleted:
        return _admin_redirect("public_user_not_found", scroll_y)
    deleted_email, deleted_phone = _soft_delete_public_user(row)
    db.commit()
    log_security_event(
        "admin_public_user_delete",
        request,
        "success",
        email=user.email,
        details={
            "deleted_public_user_id": public_user_id,
            "deleted_email": deleted_email,
            "deleted_phone": deleted_phone,
            "mode": "soft_delete",
        },
    )
    return _admin_redirect("public_user_deleted", scroll_y)


@router.post("/admin/public-users/resend-verification")
def admin_resend_public_user_verification(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_user = _admin_user_from_request(request, db)
    if not admin_user:
        return RedirectResponse(url="/admin/login", status_code=303)
    row = db.get(models.PublicUser, public_user_id)
    if not row or row.is_deleted:
        return _admin_redirect("public_user_not_found", scroll_y)
    if row.email_verified:
        return _admin_redirect("public_user_already_verified", scroll_y)

    queued, mail_info = _queue_verify_email_for_user(request, row)
    if not queued:
        log_security_event(
            "admin_public_user_resend_verification",
            request,
            "mail_failed",
            email=admin_user.email,
            details={
                "target_user_id": row.id,
                "target_email": row.email,
                "mail_error": mail_info[:200],
            },
        )
        return _admin_redirect("public_user_verification_mail_failed", scroll_y)

    row.verification_sent_at = utcnow_naive()
    db.commit()
    log_security_event(
        "admin_public_user_resend_verification",
        request,
        "success",
        email=admin_user.email,
        details={"target_user_id": row.id, "target_email": row.email, "mail_status": "queued"},
    )
    return _admin_redirect("public_user_verification_resent", scroll_y)


@router.post("/admin/public-users/restore")
def admin_restore_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_user = _admin_user_from_request(request, db)
    if not admin_user:
        return RedirectResponse(url="/admin/login", status_code=303)
    row = db.get(models.PublicUser, public_user_id)
    if not row:
        return _admin_redirect("public_user_not_found", scroll_y)
    if not row.is_deleted:
        return _admin_redirect("public_user_updated", scroll_y)
    row.is_deleted = False
    row.deleted_at = None
    row.is_active = True
    db.commit()
    log_security_event(
        "admin_public_user_restore",
        request,
        "success",
        email=admin_user.email,
        details={"restored_public_user_id": row.id, "restored_email": row.email},
    )
    return _admin_redirect("public_user_restored", scroll_y)


@router.post("/admin/public-users/bulk-action")
def admin_public_users_bulk_action(
    request: Request,
    action: str = Form(...),
    public_user_ids: list[int] = Form(default=[]),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
):
    admin_user = _admin_user_from_request(request, db)
    if not admin_user:
        return RedirectResponse(url="/admin/login", status_code=303)
    ids = sorted(set(public_user_ids))
    if not ids:
        return _admin_redirect("public_users_none_selected", scroll_y)
    rows = db.query(models.PublicUser).filter(models.PublicUser.id.in_(ids)).all()
    if not rows:
        return _admin_redirect("public_user_not_found", scroll_y)

    action_key = action.strip().lower()
    allowed = {"activate", "deactivate", "verify", "unverify", "resend_verification", "soft_delete", "restore"}
    if action_key not in allowed:
        return _admin_redirect("public_users_bulk_invalid_action", scroll_y)
    if action_key == "resend_verification":
        # Fast fail if SMTP settings are invalid.
        sample_ok, _ = validate_mailer_settings()
        if not sample_ok:
            return _admin_redirect("public_user_verification_mail_failed", scroll_y)

    updated = 0
    queued = 0
    for row in rows:
        if action_key == "activate" and not row.is_deleted:
            row.is_active = True
            updated += 1
        elif action_key == "deactivate" and not row.is_deleted:
            row.is_active = False
            updated += 1
        elif action_key == "verify" and not row.is_deleted:
            row.email_verified = True
            updated += 1
        elif action_key == "unverify" and not row.is_deleted:
            row.email_verified = False
            updated += 1
        elif action_key == "resend_verification" and (not row.is_deleted) and (not row.email_verified):
            ok, _ = _queue_verify_email_for_user(request, row)
            if ok:
                row.verification_sent_at = utcnow_naive()
                queued += 1
        elif action_key == "soft_delete" and not row.is_deleted:
            _soft_delete_public_user(row)
            updated += 1
        elif action_key == "restore" and row.is_deleted:
            row.is_deleted = False
            row.deleted_at = None
            row.is_active = True
            updated += 1
    db.commit()
    log_security_event(
        "admin_public_users_bulk_action",
        request,
        "success",
        email=admin_user.email,
        details={"action": action_key, "selected": len(ids), "updated": updated, "queued": queued},
    )
    return _admin_redirect("public_users_bulk_done", scroll_y)


@router.post("/admin/rooms")
def admin_create_room(
    name: str = Form(...),
    capacity: int = Form(10),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = models.Room(center_id=cid, name=name, capacity=capacity)
    db.add(room)
    db.commit()
    return _admin_redirect("room_created", scroll_y)


@router.post("/admin/rooms/update")
def admin_update_room(
    room_id: int = Form(...),
    name: str = Form(...),
    capacity: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")
    if capacity <= 0:
        return _admin_redirect("room_capacity_invalid", scroll_y)
    room.name = name.strip() or room.name
    room.capacity = capacity
    db.commit()
    return _admin_redirect("room_updated", scroll_y)


@router.post("/admin/rooms/delete")
def admin_delete_room(
    room_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")

    room_sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.room_id == room_id)
        .all()
    )
    if room_sessions:
        session_ids = [s.id for s in room_sessions]
        has_bookings = (
            db.query(models.Booking.id)
            .filter(models.Booking.center_id == cid, models.Booking.session_id.in_(session_ids))
            .first()
        )
        if has_bookings:
            return _admin_redirect("room_has_bookings", scroll_y)
        for session in room_sessions:
            db.delete(session)

    db.delete(room)
    db.commit()
    return _admin_redirect("room_deleted", scroll_y)


@router.post("/admin/rooms/delete-bulk")
def admin_delete_rooms_bulk(
    room_ids: list[int] = Form(default=[]),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    selected_ids = sorted(set(room_ids))
    if not selected_ids:
        return _admin_redirect("rooms_none_selected", scroll_y)

    rooms = (
        db.query(models.Room)
        .filter(models.Room.center_id == cid, models.Room.id.in_(selected_ids))
        .all()
    )
    if not rooms:
        return _admin_redirect("rooms_not_found", scroll_y)

    room_ids = [r.id for r in rooms]
    all_sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.room_id.in_(room_ids))
        .all()
    )
    sessions_by_room: dict[int, list[models.YogaSession]] = {}
    session_ids: list[int] = []
    for session in all_sessions:
        sessions_by_room.setdefault(session.room_id, []).append(session)
        session_ids.append(session.id)
    booked_session_ids: set[int] = set()
    if session_ids:
        booked_session_ids = {
            sid
            for (sid,) in db.query(models.Booking.session_id)
            .filter(models.Booking.center_id == cid, models.Booking.session_id.in_(session_ids))
            .distinct()
            .all()
        }

    blocked_bookings = 0
    deleted = 0
    for room in rooms:
        room_sessions = sessions_by_room.get(room.id, [])
        if room_sessions:
            if any(s.id in booked_session_ids for s in room_sessions):
                blocked_bookings += 1
                continue
            for session in room_sessions:
                db.delete(session)
        db.delete(room)
        deleted += 1
    db.commit()

    if deleted > 0 and blocked_bookings > 0:
        return _admin_redirect("rooms_deleted_partial_bookings", scroll_y)
    if deleted > 0:
        return _admin_redirect("rooms_deleted", scroll_y)
    if blocked_bookings > 0:
        return _admin_redirect("rooms_delete_has_bookings", scroll_y)
    return _admin_redirect("rooms_delete_blocked", scroll_y)


@router.post("/admin/sessions")
def admin_create_session(
    room_id: int = Form(...),
    title: str = Form(...),
    trainer_name: str = Form(...),
    level: str = Form(...),
    starts_at: str = Form(...),
    duration_minutes: int = Form(60),
    price_drop_in: float = Form(0.0),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff", "trainer")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        start_dt = datetime.fromisoformat(starts_at)
    except ValueError:
        start_dt = datetime.strptime(starts_at, "%Y-%m-%dT%H:%M")

    yoga_session = models.YogaSession(
        center_id=cid,
        room_id=room_id,
        title=title,
        trainer_name=trainer_name,
        level=level,
        starts_at=start_dt,
        duration_minutes=duration_minutes,
        price_drop_in=float(price_drop_in),
    )
    db.add(yoga_session)
    db.commit()
    return _admin_redirect("session_created", scroll_y)


@router.post("/admin/sessions/delete")
def admin_delete_session(
    session_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff", "trainer")),
):
    cid = require_user_center_id(user)
    yoga_session = db.get(models.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != cid:
        raise HTTPException(status_code=404, detail="Session not found")

    booking_ids = [b.id for b in db.query(models.Booking).filter(models.Booking.session_id == session_id).all()]
    if booking_ids:
        db.query(models.Payment).filter(models.Payment.booking_id.in_(booking_ids)).delete(
            synchronize_session=False
        )
    db.query(models.Booking).filter(models.Booking.session_id == session_id).delete()
    db.delete(yoga_session)
    db.commit()
    return _admin_redirect("session_deleted", scroll_y)


@router.post("/admin/plans")
def admin_create_plan(
    name: str = Form(...),
    plan_type: str = Form(...),
    price: float = Form(...),
    session_limit: str = Form(default=""),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    if plan_type not in ("weekly", "monthly", "yearly"):
        raise HTTPException(status_code=400, detail="Invalid plan type")
    if price < 0:
        raise HTTPException(status_code=400, detail="Price must be non-negative")
    parsed_session_limit = None
    if session_limit.strip():
        try:
            parsed_session_limit = int(session_limit)
        except ValueError:
            raise HTTPException(status_code=400, detail="Session limit must be an integer")
        if parsed_session_limit <= 0:
            parsed_session_limit = None
    plan = models.SubscriptionPlan(
        center_id=cid,
        name=name,
        plan_type=plan_type,
        price=price,
        session_limit=parsed_session_limit,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return _admin_redirect("plan_created", scroll_y)


@router.post("/admin/plans/update-name")
def admin_update_plan_name(
    plan_id: int = Form(...),
    name: str = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")
    new_name = name.strip()
    if not new_name:
        return _admin_redirect("plan_name_invalid", scroll_y)
    plan.name = new_name
    db.commit()
    return _admin_redirect("plan_updated", scroll_y)


@router.post("/admin/plans/update-details")
def admin_update_plan_details(
    plan_id: int = Form(...),
    plan_type: str = Form(...),
    price: float = Form(...),
    session_limit: str = Form(default=""),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_type_clean = plan_type.strip().lower()
    if plan_type_clean not in ("weekly", "monthly", "yearly"):
        return _admin_redirect("plan_details_invalid", scroll_y)
    if price < 0:
        return _admin_redirect("plan_details_invalid", scroll_y)

    parsed_session_limit = None
    if session_limit.strip():
        try:
            parsed_session_limit = int(session_limit)
        except ValueError:
            return _admin_redirect("plan_details_invalid", scroll_y)
        if parsed_session_limit <= 0:
            return _admin_redirect("plan_details_invalid", scroll_y)

    plan.plan_type = plan_type_clean
    plan.price = float(price)
    plan.session_limit = parsed_session_limit
    db.commit()
    return _admin_redirect("plan_details_updated", scroll_y)


@router.post("/admin/plans/delete")
def admin_delete_plan(
    plan_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")
    has_subscriptions = db.query(models.ClientSubscription).filter(models.ClientSubscription.plan_id == plan_id).first()
    if has_subscriptions:
        return _admin_redirect("plan_has_subscriptions", scroll_y)
    db.delete(plan)
    db.commit()
    return _admin_redirect("plan_deleted", scroll_y)


@router.post("/admin/faqs")
def admin_create_faq(
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    is_active: str = Form("1"),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    q = question.strip()
    a = answer.strip()
    if not q or not a:
        return _admin_redirect("faq_invalid", scroll_y)
    row = models.FAQItem(
        center_id=cid,
        question=q,
        answer=a,
        sort_order=max(0, int(sort_order)),
        is_active=is_active in {"1", "true", "on", "yes"},
    )
    db.add(row)
    db.commit()
    return _admin_redirect("faq_created", scroll_y)


@router.post("/admin/faqs/update")
def admin_update_faq(
    faq_id: int = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    is_active: str = Form("1"),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FAQItem, faq_id)
    if not row or row.center_id != cid:
        return _admin_redirect("faq_not_found", scroll_y)
    q = question.strip()
    a = answer.strip()
    if not q or not a:
        return _admin_redirect("faq_invalid", scroll_y)
    row.question = q
    row.answer = a
    row.sort_order = max(0, int(sort_order))
    row.is_active = is_active in {"1", "true", "on", "yes"}
    db.commit()
    return _admin_redirect("faq_updated", scroll_y)


@router.post("/admin/faqs/delete")
def admin_delete_faq(
    faq_id: int = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FAQItem, faq_id)
    if not row or row.center_id != cid:
        return _admin_redirect("faq_not_found", scroll_y)
    db.delete(row)
    db.commit()
    return _admin_redirect("faq_deleted", scroll_y)


@router.post("/admin/faqs/reorder")
def admin_reorder_faqs(
    ordered_ids_csv: str = Form(...),
    scroll_y: str = Form(default=""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    raw = [x.strip() for x in ordered_ids_csv.split(",") if x.strip()]
    if not raw:
        return _admin_redirect("faq_reorder_invalid", scroll_y)
    try:
        ids = [int(x) for x in raw]
    except ValueError:
        return _admin_redirect("faq_reorder_invalid", scroll_y)
    unique_ids = list(dict.fromkeys(ids))
    rows = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == cid, models.FAQItem.id.in_(unique_ids))
        .all()
    )
    if len(rows) != len(unique_ids):
        return _admin_redirect("faq_reorder_invalid", scroll_y)
    row_by_id = {r.id: r for r in rows}
    for idx, faq_id in enumerate(unique_ids, start=1):
        row_by_id[faq_id].sort_order = idx
    db.commit()
    return _admin_redirect("faq_reordered", scroll_y)


@router.post("/public/subscribe")
def public_subscribe(
    request: Request,
    center_id: int = Form(...),
    plan_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != center_id or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    start_date = utcnow_naive()
    end_date = start_date + timedelta(days=_plan_duration_days(plan.plan_type))
    subscription = models.ClientSubscription(
        client_id=client.id,
        plan_id=plan.id,
        start_date=start_date,
        end_date=end_date,
        status="pending",
    )
    db.add(subscription)
    db.flush()

    payment_row = models.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=None,
        amount=float(plan.price),
        currency="SAR",
        payment_method=f"subscription_{plan.plan_type}",
        status="pending",
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)
    db.refresh(subscription)

    provider = get_payment_provider()
    base = _public_base(request)
    if isinstance(provider, StripePaymentProvider):
        try:
            provider_result = provider.create_checkout_session(
                amount=float(plan.price),
                currency="sar",
                metadata={
                    "payment_id": str(payment_row.id),
                    "subscription_id": str(subscription.id),
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                    "plan_id": str(plan.id),
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success&msg=subscribed",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled&msg=subscription_cancelled",
            )
        except Exception as exc:
            payment_row.status = "failed"
            subscription.status = "cancelled"
            db.commit()
            log_security_event(
                "public_subscribe",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id, "plan_id": plan_id},
            )
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_error",
                status_code=303,
            )

        payment_row.provider_ref = provider_result.provider_ref
        db.commit()
        checkout_url = provider_result.checkout_url or ""
        if not checkout_url:
            payment_row.status = "failed"
            subscription.status = "cancelled"
            db.commit()
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_no_url", status_code=303)
        return RedirectResponse(url=checkout_url, status_code=303)

    provider_result = provider.charge(
        amount=float(plan.price),
        currency="SAR",
        metadata={
            "center_id": center_id,
            "client_id": client.id,
            "plan_id": plan.id,
            "subscription_id": subscription.id,
        },
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    subscription.status = "active" if provider_result.status == "paid" else "cancelled"
    db.commit()
    return RedirectResponse(url=f"/index?center_id={center_id}&msg=subscribed_mock", status_code=303)

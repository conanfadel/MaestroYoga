"""Admin HTML routes."""
import csv
import io
import json
from html import escape as html_escape
from collections import defaultdict
from datetime import date, datetime, timedelta
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import and_, case, func, nullslast, or_
from sqlalchemy.orm import Session

from .. import models
from ..booking_utils import ACTIVE_BOOKING_STATUSES, spots_available
from ..bootstrap import DEMO_CENTER_NAME, ensure_demo_data, ensure_demo_news_posts
from ..database import get_db
from ..loyalty import (
    LOYALTY_REWARD_MAX_LEN,
    count_confirmed_sessions_for_public_user,
    effective_loyalty_thresholds,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_program_table_rows,
    loyalty_thresholds,
    validate_loyalty_threshold_triple,
)
from ..mailer import (
    feedback_destination_email,
    queue_email_verification_email,
    queue_password_reset_email,
    send_mail_with_attachments,
    validate_mailer_settings,
)
from ..payments import get_payment_provider, payment_provider_supports_hosted_checkout
from ..rate_limiter import rate_limiter
from ..request_ip import get_client_ip
from ..security_audit import log_security_event
from ..security import (
    create_access_token,
    create_public_access_token,
    create_public_email_verification_token,
    create_public_email_verify_flash_token,
    create_public_password_reset_token,
    decode_public_email_verification_token,
    decode_public_email_verify_flash_token,
    decode_public_password_reset_token,
    get_public_user_from_token_string,
    get_user_from_token_string,
    hash_password,
    require_roles_cookie_or_bearer,
    verify_password,
)
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..web_shared import (
    _cookie_secure_flag,
    _fmt_dt,
    _fmt_dt_weekday_ar,
    _is_email_verification_required,
    _is_strong_public_password,
    _is_truthy_env,
    _normalize_phone_with_country,
    _plan_duration_days,
    _public_base,
    _sanitize_next_url,
    PUBLIC_INDEX_DEFAULT_PATH,
    public_center_id_str_from_next,
    public_index_url_from_next,
    public_mail_fail_why_token,
    _url_with_params,
)
from .constants import *
from .helpers import *
from .router import router
from .templates_env import templates

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
    email_norm = (email or "").strip().lower()
    user = db.query(models.User).filter(models.User.email == email_norm).first()
    if not user or not verify_password(password, user.password_hash):
        log_security_event(
            "admin_login",
            request,
            "invalid_credentials",
            email=email_norm,
        )
        return RedirectResponse(url="/admin/login?error=1", status_code=303)
    if user.role not in ("center_owner", "center_staff", "trainer"):
        log_security_event(
            "admin_login",
            request,
            "forbidden_role",
            email=user.email,
        )
        return RedirectResponse(url="/admin/login?error=role", status_code=303)

    log_security_event("admin_login", request, "success", email=user.email)
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
    room_sort: str = "id_asc",
    public_user_q: str = "",
    public_user_status: str = "active",
    public_user_verified: str = "all",
    public_user_page: int = 1,
    trash_page: int = 1,
    trash_q: str = "",
    sessions_page: int = 1,
    payments_page: int = 1,
    audit_event_type: str = "",
    audit_status: str = "",
    audit_email: str = "",
    audit_ip: str = "",
    audit_page: int = 1,
    payment_date_from: str = "",
    payment_date_to: str = "",
    post_edit: int = 0,
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    if center:
        if center.name == DEMO_CENTER_NAME:
            ensure_demo_news_posts(db, center.id)
        _clear_center_branding_urls_if_files_missing(db, center)
    room_sort_key = (room_sort or "id_asc").strip().lower()
    room_ordering = {
        "id_asc": (models.Room.id.asc(),),
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
        room_order_by = room_ordering.get(room_sort_key, room_ordering["id_asc"])
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
    rooms_by_id = {r.id: r for r in rooms}

    def _normalize_page(page_value: int, total_items: int, page_size: int) -> tuple[int, int, int]:
        safe_page = max(1, int(page_value or 1))
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        if safe_page > total_pages:
            safe_page = total_pages
        offset = (safe_page - 1) * page_size
        return safe_page, total_pages, offset

    sessions_page_size = ADMIN_SESSIONS_PAGE_SIZE
    sessions_base_query = db.query(models.YogaSession).filter(models.YogaSession.center_id == cid)
    sessions_total = sessions_base_query.order_by(None).count()
    safe_sessions_page, sessions_total_pages, sessions_offset = _normalize_page(
        sessions_page,
        sessions_total,
        sessions_page_size,
    )
    sessions = (
        sessions_base_query.order_by(models.YogaSession.starts_at.desc())
        .offset(sessions_offset)
        .limit(sessions_page_size)
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
    public_users_page_size = ADMIN_PUBLIC_USERS_PAGE_SIZE
    public_users_total = public_users_query.order_by(None).count()
    safe_public_user_page, public_users_total_pages, public_users_offset = _normalize_page(
        public_user_page,
        public_users_total,
        public_users_page_size,
    )
    public_users = (
        public_users_query.order_by(models.PublicUser.created_at.desc())
        .offset(public_users_offset)
        .limit(public_users_page_size)
        .all()
    )
    trash_q_s = trash_q.strip()
    trash_base = db.query(models.PublicUser).filter(models.PublicUser.is_deleted.is_(True))
    if trash_q_s:
        trash_base = trash_base.filter(
            or_(
                models.PublicUser.full_name.ilike(f"%{trash_q_s}%"),
                models.PublicUser.email.ilike(f"%{trash_q_s}%"),
            )
        )
    trash_total = trash_base.order_by(None).count()
    safe_trash_page, trash_total_pages, trash_offset = _normalize_page(
        trash_page,
        trash_total,
        public_users_page_size,
    )
    trash_users_list = (
        trash_base.order_by(models.PublicUser.deleted_at.desc(), models.PublicUser.id.desc())
        .offset(trash_offset)
        .limit(public_users_page_size)
        .all()
    )
    session_rows = []
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
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
    tomorrow_d = today + timedelta(days=1)
    now_na = utcnow_naive()
    payment_from_dt = _parse_optional_date_str(payment_date_from)
    payment_to_dt = _parse_optional_date_str(payment_date_to)

    sessions_today_no_bookings = (
        db.query(models.YogaSession.id)
        .outerjoin(
            models.Booking,
            and_(
                models.Booking.session_id == models.YogaSession.id,
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            ),
        )
        .filter(
            models.YogaSession.center_id == cid,
            func.date(models.YogaSession.starts_at) == today,
        )
        .group_by(models.YogaSession.id)
        .having(func.count(models.Booking.id) == 0)
        .count()
    )
    subs_expiring_7d = (
        db.query(models.ClientSubscription)
        .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
        .filter(
            models.Client.center_id == cid,
            models.ClientSubscription.status == "active",
            models.ClientSubscription.end_date >= now_na,
            models.ClientSubscription.end_date <= now_na + timedelta(days=7),
        )
        .count()
    )
    public_users_unverified_count = (
        db.query(models.PublicUser)
        .filter(
            models.PublicUser.is_deleted.is_(False),
            models.PublicUser.is_active.is_(True),
            models.PublicUser.email_verified.is_(False),
        )
        .count()
    )

    revenue_7d_bars: list[dict[str, Any]] = []
    max_rev_7d = 0.01
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        amt = float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "paid",
                func.date(models.Payment.paid_at) == d,
            )
            .scalar()
            or 0.0
        )
        revenue_7d_bars.append({"date_iso": d.isoformat(), "amount": amt, "label": f"{d.day}/{d.month}"})
        max_rev_7d = max(max_rev_7d, amt)
    for bar in revenue_7d_bars:
        bar["bar_pct"] = int(round(100 * float(bar["amount"]) / max_rev_7d)) if max_rev_7d > 0 else 0

    ops_sessions_q = (
        db.query(models.YogaSession)
        .filter(
            models.YogaSession.center_id == cid,
            or_(
                func.date(models.YogaSession.starts_at) == today,
                func.date(models.YogaSession.starts_at) == tomorrow_d,
            ),
        )
        .order_by(models.YogaSession.starts_at.asc())
        .limit(36)
        .all()
    )
    ops_today_rows: list[dict[str, str | int]] = []
    ops_tomorrow_rows: list[dict[str, str | int]] = []
    for s in ops_sessions_q:
        room = rooms_by_id.get(s.room_id)
        row = {
            "id": s.id,
            "title": s.title,
            "trainer": s.trainer_name,
            "room": room.name if room else "-",
            "starts": _fmt_dt(s.starts_at),
            "spots": spots_available(db, s),
            "capacity": room.capacity if room else 0,
        }
        if s.starts_at.date() == today:
            ops_today_rows.append(row)
        elif s.starts_at.date() == tomorrow_d:
            ops_tomorrow_rows.append(row)

    window_start = now_na - timedelta(hours=6)
    future_for_conflicts = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.starts_at >= window_start)
        .order_by(models.YogaSession.room_id, models.YogaSession.starts_at)
        .all()
    )
    by_room_sessions: dict[int, list[models.YogaSession]] = defaultdict(list)
    for s in future_for_conflicts:
        by_room_sessions[s.room_id].append(s)
    schedule_conflicts: list[dict[str, str | int]] = []
    for rid, lst in by_room_sessions.items():
        lst.sort(key=lambda x: x.starts_at)
        for i in range(len(lst) - 1):
            a, b = lst[i], lst[i + 1]
            end_a = a.starts_at + timedelta(minutes=int(a.duration_minutes or 0))
            if end_a > b.starts_at:
                schedule_conflicts.append(
                    {
                        "room_name": (rooms_by_id.get(rid).name if rooms_by_id.get(rid) else f"غرفة #{rid}"),
                        "a_id": a.id,
                        "a_title": a.title,
                        "a_start": _fmt_dt(a.starts_at),
                        "b_id": b.id,
                        "b_title": b.title,
                        "b_start": _fmt_dt(b.starts_at),
                    }
                )

    admin_login_audit_rows = [
        {
            "created_at_display": _fmt_dt(ev.created_at),
            "status": ev.status,
            "email": ev.email or "-",
            "ip": ev.ip or "-",
        }
        for ev in db.query(models.SecurityAuditEvent)
        .filter(models.SecurityAuditEvent.event_type == "admin_login")
        .order_by(models.SecurityAuditEvent.created_at.desc())
        .limit(20)
        .all()
    ]

    recent_public_cutoff = utcnow_naive() - timedelta(days=7)
    paid_revenue_total, paid_revenue_today = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (models.Payment.status == "paid", models.Payment.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.Payment.status == "paid",
                                func.date(models.Payment.paid_at) == today,
                            ),
                            models.Payment.amount,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
        )
        .filter(models.Payment.center_id == cid)
        .one()
    )
    public_users_count, public_users_deleted_count, public_users_new_7d = (
        db.query(
            func.count(models.PublicUser.id),
            func.coalesce(
                func.sum(case((models.PublicUser.is_deleted.is_(True), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                models.PublicUser.created_at >= recent_public_cutoff,
                                models.PublicUser.is_deleted.is_(False),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).one()
    )
    dashboard = {
        "rooms_count": len(rooms),
        "sessions_count": sessions_total,
        "bookings_count": db.query(models.Booking).filter(models.Booking.center_id == cid).count(),
        "clients_count": db.query(models.Client).filter(models.Client.center_id == cid).count(),
        "active_plans_count": sum(1 for p in plans if p.is_active),
        "active_subscriptions_count": (
            db.query(models.ClientSubscription)
            .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
            .filter(
                models.Client.center_id == cid,
                models.ClientSubscription.status == "active",
            )
            .count()
        ),
        "revenue_total": float(paid_revenue_total or 0.0),
        "revenue_today": float(paid_revenue_today or 0.0),
        "public_users_count": int(public_users_count) - int(public_users_deleted_count),
        "public_users_deleted_count": int(public_users_deleted_count),
        "public_users_new_7d": int(public_users_new_7d),
    }
    payments_page_size = ADMIN_PAYMENTS_PAGE_SIZE
    payments_base_query = db.query(models.Payment).filter(models.Payment.center_id == cid)
    if payment_from_dt:
        payments_base_query = payments_base_query.filter(func.date(models.Payment.paid_at) >= payment_from_dt)
    if payment_to_dt:
        payments_base_query = payments_base_query.filter(func.date(models.Payment.paid_at) <= payment_to_dt)
    payments_total = payments_base_query.order_by(None).count()
    safe_payments_page, payments_total_pages, payments_offset = _normalize_page(
        payments_page,
        payments_total,
        payments_page_size,
    )
    recent_payments = (
        payments_base_query.order_by(models.Payment.paid_at.desc())
        .offset(payments_offset)
        .limit(payments_page_size)
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
    loyalty_by_email = loyalty_confirmed_counts_by_email_lower(db, cid)
    public_user_rows = []
    for u in public_users:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = loyalty_context_for_count(cnt, center=center)
        public_user_rows.append(
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
                "loyalty_confirmed_count": cnt,
                "loyalty_tier": lt["loyalty_tier"],
                "loyalty_tier_label": lt["loyalty_tier_label"],
            }
        )
    trash_user_rows = []
    for u in trash_users_list:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = loyalty_context_for_count(cnt, center=center)
        trash_user_rows.append(
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone or "-",
                "deleted_at_display": _fmt_dt(u.deleted_at),
                "created_at_display": _fmt_dt(u.created_at),
                "loyalty_confirmed_count": cnt,
                "loyalty_tier": lt["loyalty_tier"],
                "loyalty_tier_label": lt["loyalty_tier_label"],
            }
        )
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

    audit_page_size = ADMIN_SECURITY_AUDIT_PAGE_SIZE
    security_events_total = audit_query.order_by(None).count()
    safe_audit_page, security_events_total_pages, security_events_offset = _normalize_page(
        audit_page,
        security_events_total,
        audit_page_size,
    )
    security_events = (
        audit_query.order_by(models.SecurityAuditEvent.created_at.desc())
        .offset(security_events_offset)
        .limit(audit_page_size)
        .all()
    )
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
    admin_flash = None
    if msg:
        flash_data = ADMIN_FLASH_MESSAGES.get(msg)
        if flash_data:
            text, level = flash_data
            admin_flash = {"text": text, "level": level}

    base_admin_params = {
        ADMIN_QP_ROOM_SORT: room_sort,
        ADMIN_QP_PUBLIC_USER_Q: public_user_q,
        ADMIN_QP_PUBLIC_USER_STATUS: public_user_status,
        ADMIN_QP_PUBLIC_USER_VERIFIED: public_user_verified,
        ADMIN_QP_PUBLIC_USER_PAGE: str(safe_public_user_page),
        ADMIN_QP_TRASH_PAGE: str(safe_trash_page),
        ADMIN_QP_TRASH_Q: trash_q,
        ADMIN_QP_SESSIONS_PAGE: str(safe_sessions_page),
        ADMIN_QP_PAYMENTS_PAGE: str(safe_payments_page),
        ADMIN_QP_AUDIT_EVENT_TYPE: audit_event_type,
        ADMIN_QP_AUDIT_STATUS: audit_status,
        ADMIN_QP_AUDIT_EMAIL: audit_email,
        ADMIN_QP_AUDIT_IP: audit_ip,
        ADMIN_QP_AUDIT_PAGE: str(safe_audit_page),
        ADMIN_QP_PAYMENT_DATE_FROM: (payment_date_from or "").strip()[:32],
        ADMIN_QP_PAYMENT_DATE_TO: (payment_date_to or "").strip()[:32],
    }

    def _admin_page_url(**overrides: str) -> str:
        params = dict(base_admin_params)
        for k, v in overrides.items():
            params[k] = v
        return _url_with_params("/admin", **params)

    public_users_page_prev_url = _admin_page_url(**{ADMIN_QP_PUBLIC_USER_PAGE: str(max(1, safe_public_user_page - 1))})
    public_users_page_next_url = _admin_page_url(
        **{ADMIN_QP_PUBLIC_USER_PAGE: str(min(public_users_total_pages, safe_public_user_page + 1))}
    )
    security_page_prev_url = _admin_page_url(**{ADMIN_QP_AUDIT_PAGE: str(max(1, safe_audit_page - 1))})
    security_page_next_url = _admin_page_url(
        **{ADMIN_QP_AUDIT_PAGE: str(min(security_events_total_pages, safe_audit_page + 1))}
    )
    sessions_page_prev_url = _admin_page_url(**{ADMIN_QP_SESSIONS_PAGE: str(max(1, safe_sessions_page - 1))})
    sessions_page_next_url = _admin_page_url(
        **{ADMIN_QP_SESSIONS_PAGE: str(min(sessions_total_pages, safe_sessions_page + 1))}
    )
    payments_page_prev_url = _admin_page_url(**{ADMIN_QP_PAYMENTS_PAGE: str(max(1, safe_payments_page - 1))})
    payments_page_next_url = _admin_page_url(
        **{ADMIN_QP_PAYMENTS_PAGE: str(min(payments_total_pages, safe_payments_page + 1))}
    )
    trash_page_prev_url = _admin_page_url(**{ADMIN_QP_TRASH_PAGE: str(max(1, safe_trash_page - 1))})
    trash_page_next_url = _admin_page_url(
        **{ADMIN_QP_TRASH_PAGE: str(min(trash_total_pages, safe_trash_page + 1))}
    )

    safe_post_edit = max(0, int(post_edit or 0))
    center_posts_all = (
        db.query(models.CenterPost)
        .filter(models.CenterPost.center_id == cid)
        .order_by(models.CenterPost.updated_at.desc())
        .all()
    )

    def _post_admin_edit_url(edit_id: int) -> str:
        return _admin_page_url(**{ADMIN_QP_POST_EDIT: str(edit_id)}) + "#section-center-posts"

    center_post_admin_rows: list[dict[str, str | int | bool]] = []
    for cp in center_posts_all:
        center_post_admin_rows.append(
            {
                "id": cp.id,
                "title": cp.title,
                "post_type": cp.post_type,
                "type_label": CENTER_POST_TYPE_LABELS.get(cp.post_type, cp.post_type),
                "is_published": cp.is_published,
                "is_pinned": cp.is_pinned,
                "updated_display": _fmt_dt(cp.updated_at),
                "gallery_count": len(cp.images),
                "public_url": _url_with_params("/post", center_id=str(cid), post_id=str(cp.id))
                if cp.is_published
                else "",
                "edit_url": _post_admin_edit_url(cp.id),
            }
        )

    editing_post: dict[str, Any] | None = None
    if safe_post_edit:
        ep = db.get(models.CenterPost, safe_post_edit)
        if ep and ep.center_id == cid:
            gi = sorted(ep.images, key=lambda x: (x.sort_order, x.id))
            editing_post = {
                "id": ep.id,
                "title": ep.title,
                "summary": ep.summary or "",
                "body": ep.body or "",
                "post_type": ep.post_type,
                "is_pinned": ep.is_pinned,
                "is_published": ep.is_published,
                "cover_image_url": ep.cover_image_url or "",
                "gallery": [{"id": g.id, "url": g.image_url} for g in gi],
            }

    center_post_type_choices = [
        {"value": k, "label": v} for k, v in sorted(CENTER_POST_TYPE_LABELS.items(), key=lambda x: x[1])
    ]

    dash_home = _admin_page_url()
    admin_insights: list[dict[str, str]] = []
    if sessions_today_no_bookings:
        admin_insights.append(
            {
                "label": f"جلسات اليوم بلا حجوزات نشطة: {sessions_today_no_bookings}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )
    if subs_expiring_7d:
        admin_insights.append(
            {
                "label": f"اشتراكات تنتهي خلال 7 أيام: {subs_expiring_7d}",
                "href": f"{dash_home}#section-plans",
                "kind": "info",
            }
        )
    if public_users_unverified_count:
        admin_insights.append(
            {
                "label": f"مستخدمون غير موثّقين (عام): {public_users_unverified_count}",
                "href": f"{dash_home}#section-public-users",
                "kind": "info",
            }
        )
    if schedule_conflicts:
        admin_insights.append(
            {
                "label": f"تضارب جدولة في نفس الغرفة: {len(schedule_conflicts)}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )

    export_pay_params: dict[str, str] = {}
    pf = (payment_date_from or "").strip()[:32]
    pt = (payment_date_to or "").strip()[:32]
    if pf:
        export_pay_params[ADMIN_QP_PAYMENT_DATE_FROM] = pf
    if pt:
        export_pay_params[ADMIN_QP_PAYMENT_DATE_TO] = pt
    data_export_urls = {
        "clients": "/admin/export/clients.csv",
        "bookings": "/admin/export/bookings.csv",
        "payments": _url_with_params("/admin/export/payments.csv", **export_pay_params)
        if export_pay_params
        else "/admin/export/payments.csv",
    }

    _env_b, _env_s, _env_g = loyalty_thresholds()
    _eff_b, _eff_s, _eff_g = effective_loyalty_thresholds(center)
    loyalty_admin = {
        "env": {"bronze": _env_b, "silver": _env_s, "gold": _env_g},
        "effective": {"bronze": _eff_b, "silver": _eff_s, "gold": _eff_g},
    }

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "center": center,
            "msg": msg,
            "admin_flash": admin_flash,
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
            "public_user_pagination": {
                "page": safe_public_user_page,
                "page_size": public_users_page_size,
                "total": public_users_total,
                "total_pages": public_users_total_pages,
                "has_prev": safe_public_user_page > 1,
                "has_next": safe_public_user_page < public_users_total_pages,
                "prev_url": public_users_page_prev_url,
                "next_url": public_users_page_next_url,
            },
            "trash_users": trash_user_rows,
            "trash_filters": {"q": trash_q},
            "trash_pagination": {
                "page": safe_trash_page,
                "page_size": public_users_page_size,
                "total": trash_total,
                "total_pages": trash_total_pages,
                "has_prev": safe_trash_page > 1,
                "has_next": safe_trash_page < trash_total_pages,
                "prev_url": trash_page_prev_url,
                "next_url": trash_page_next_url,
            },
            "security_pagination": {
                "page": safe_audit_page,
                "page_size": audit_page_size,
                "total": security_events_total,
                "total_pages": security_events_total_pages,
                "has_prev": safe_audit_page > 1,
                "has_next": safe_audit_page < security_events_total_pages,
                "prev_url": security_page_prev_url,
                "next_url": security_page_next_url,
            },
            "sessions_pagination": {
                "page": safe_sessions_page,
                "page_size": sessions_page_size,
                "total": sessions_total,
                "total_pages": sessions_total_pages,
                "has_prev": safe_sessions_page > 1,
                "has_next": safe_sessions_page < sessions_total_pages,
                "prev_url": sessions_page_prev_url,
                "next_url": sessions_page_next_url,
            },
            "payments_pagination": {
                "page": safe_payments_page,
                "page_size": payments_page_size,
                "total": payments_total,
                "total_pages": payments_total_pages,
                "has_prev": safe_payments_page > 1,
                "has_next": safe_payments_page < payments_total_pages,
                "prev_url": payments_page_prev_url,
                "next_url": payments_page_next_url,
            },
            "room_filters": {
                "sort": (
                    room_sort_key
                    if room_sort_key in room_ordering or room_sort_key in {"sessions_desc", "sessions_asc"}
                    else "id_asc"
                ),
            },
            "center_id": cid,
            "admin_public_index_url": _url_with_params("/index", center_id=str(cid)),
            "admin_insights": admin_insights,
            "revenue_7d_bars": revenue_7d_bars,
            "ops_today_rows": ops_today_rows,
            "ops_tomorrow_rows": ops_tomorrow_rows,
            "schedule_conflicts": schedule_conflicts,
            "admin_login_audit_rows": admin_login_audit_rows,
            "data_export_urls": data_export_urls,
            "payment_date_from_value": pf,
            "payment_date_to_value": pt,
            "loyalty_admin": loyalty_admin,
            "is_trainer": user.role == "trainer",
            "is_center_owner": user.role == "center_owner",
            "show_security_section": user.role == "center_owner",
            "center_post_admin_rows": center_post_admin_rows,
            "editing_post": editing_post,
            "center_post_type_choices": center_post_type_choices,
            "post_edit_id": safe_post_edit,
        },
    )

@router.get("/admin/export/clients.csv")
def export_clients_csv(request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_user_for_data_export(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    rows = (
        db.query(models.Client)
        .filter(models.Client.center_id == cid)
        .order_by(models.Client.created_at.desc())
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "full_name", "email", "phone", "created_at"])
    for c in rows:
        writer.writerow(
            [
                c.id,
                c.full_name,
                c.email,
                c.phone or "",
                c.created_at.isoformat() if c.created_at else "",
            ]
        )
    content = _utf8_bom_csv_content(output)
    output.close()
    fn = f"clients_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/admin/export/bookings.csv")
def export_bookings_csv(request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_user_for_data_export(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    q = (
        db.query(models.Booking, models.YogaSession, models.Client)
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .join(models.Client, models.Client.id == models.Booking.client_id)
        .filter(models.Booking.center_id == cid)
        .order_by(models.Booking.booked_at.desc())
        .limit(50_000)
        .all()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "booking_id",
            "status",
            "booked_at",
            "session_id",
            "session_title",
            "session_starts_at",
            "client_id",
            "client_name",
            "client_email",
        ]
    )
    for bk, sess, cl in q:
        writer.writerow(
            [
                bk.id,
                bk.status,
                bk.booked_at.isoformat() if bk.booked_at else "",
                sess.id,
                sess.title,
                sess.starts_at.isoformat() if sess.starts_at else "",
                cl.id,
                cl.full_name,
                cl.email,
            ]
        )
    content = _utf8_bom_csv_content(output)
    output.close()
    fn = f"bookings_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/admin/export/payments.csv")
def export_payments_csv(
    request: Request,
    payment_date_from: str = "",
    payment_date_to: str = "",
    db: Session = Depends(get_db),
):
    user, redirect = _admin_user_for_data_export(request, db)
    if redirect:
        return redirect
    assert user is not None
    cid = require_user_center_id(user)
    pq = db.query(models.Payment).filter(models.Payment.center_id == cid)
    pdf = _parse_optional_date_str(payment_date_from)
    pdt = _parse_optional_date_str(payment_date_to)
    if pdf:
        pq = pq.filter(func.date(models.Payment.paid_at) >= pdf)
    if pdt:
        pq = pq.filter(func.date(models.Payment.paid_at) <= pdt)
    rows = pq.order_by(models.Payment.paid_at.desc()).limit(50_000).all()
    client_ids = list({p.client_id for p in rows})
    clients_map = {
        c.id: c
        for c in db.query(models.Client).filter(models.Client.id.in_(client_ids)).all()
    } if client_ids else {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["payment_id", "client_id", "client_name", "amount", "currency", "status", "method", "paid_at", "booking_id"]
    )
    for p in rows:
        cl = clients_map.get(p.client_id)
        writer.writerow(
            [
                p.id,
                p.client_id,
                cl.full_name if cl else "",
                p.amount,
                p.currency,
                p.status,
                p.payment_method,
                p.paid_at.isoformat() if p.paid_at else "",
                p.booking_id or "",
            ]
        )
    content = _utf8_bom_csv_content(output)
    output.close()
    fn = f"payments_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
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
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role != "center_owner":
        return _security_owner_forbidden_redirect()

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
    minutes: int = Form(ADMIN_IP_BLOCK_DEFAULT_MINUTES),
    reason: str = Form("manual_block"),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role != "center_owner":
        return _security_owner_forbidden_redirect(return_section)

    target_ip = ip.strip()
    if not target_ip:
        return _admin_redirect(ADMIN_MSG_IP_BLOCK_INVALID, return_section=return_section)
    if minutes <= 0:
        minutes = ADMIN_IP_BLOCK_DEFAULT_MINUTES
    if minutes > ADMIN_IP_BLOCK_MAX_MINUTES:
        minutes = ADMIN_IP_BLOCK_MAX_MINUTES
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
    return _admin_redirect(ADMIN_MSG_IP_BLOCKED, return_section=return_section)


@router.post("/admin/security/ip-unblock")
def admin_unblock_ip(
    request: Request,
    ip: str = Form(...),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role != "center_owner":
        return _security_owner_forbidden_redirect(return_section)
    target_ip = ip.strip()
    if not target_ip:
        return _admin_redirect(ADMIN_MSG_IP_BLOCK_INVALID, return_section=return_section)
    row = db.query(models.BlockedIP).filter(models.BlockedIP.ip == target_ip).first()
    if not row:
        return _admin_redirect(ADMIN_MSG_IP_UNBLOCK_NOT_FOUND, return_section=return_section)
    row.is_active = False
    db.commit()
    log_security_event(
        "admin_ip_unblock",
        request,
        "success",
        email=user.email,
        details={"target_ip": target_ip, "reason": "manual_unblock"},
    )
    return _admin_redirect(ADMIN_MSG_IP_UNBLOCKED, return_section=return_section)


@router.post("/admin/public-users/toggle-active")
def admin_toggle_public_user_active(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    row.is_active = not row.is_active
    db.commit()
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)


@router.post("/admin/public-users/toggle-verified")
def admin_toggle_public_user_verified(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    row.email_verified = not row.email_verified
    db.commit()
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)


@router.post("/admin/public-users/delete")
def admin_delete_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert user is not None
    if user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
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
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_DELETED, scroll_y, return_section)


@router.post("/admin/public-users/resend-verification")
def admin_resend_public_user_verification(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(db, public_user_id, scroll_y, return_section=return_section)
    if redirect:
        return redirect
    assert row is not None
    if row.email_verified:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_ALREADY_VERIFIED, scroll_y, return_section)

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
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED, scroll_y, return_section)

    row.verification_sent_at = utcnow_naive()
    db.commit()
    log_security_event(
        "admin_public_user_resend_verification",
        request,
        "success",
        email=admin_user.email,
        details={"target_user_id": row.id, "target_email": row.email, "mail_status": "queued"},
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_VERIFICATION_RESENT, scroll_y, return_section)


@router.post("/admin/public-users/restore")
def admin_restore_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(
        db, public_user_id, scroll_y, allow_deleted=True, return_section=return_section
    )
    if redirect:
        return redirect
    assert row is not None
    if not row.is_deleted:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)
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
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_RESTORED, scroll_y, return_section)


@router.post("/admin/public-users/permanent-delete")
def admin_permanent_delete_public_user(
    request: Request,
    public_user_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    row, redirect = _get_public_user_or_redirect(
        db, public_user_id, scroll_y, allow_deleted=True, return_section=return_section
    )
    if redirect:
        return redirect
    assert row is not None
    if not row.is_deleted:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETE_FORBIDDEN, scroll_y, return_section)
    uid = row.id
    tomb_email = row.email
    db.delete(row)
    db.commit()
    log_security_event(
        "admin_public_user_permanent_delete",
        request,
        "success",
        email=admin_user.email,
        details={"target_public_user_id": uid, "tombstone_email": tomb_email},
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETED, scroll_y, return_section)


@router.post("/admin/public-users/bulk-action")
def admin_public_users_bulk_action(
    request: Request,
    action: str = Form(...),
    public_user_ids: list[int] = Form(default=[]),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
):
    admin_user, redirect = _require_admin_user_or_redirect(request, db)
    if redirect:
        return redirect
    assert admin_user is not None
    if admin_user.role == "trainer":
        return _trainer_forbidden_redirect(return_section)
    ids = sorted(set(public_user_ids))
    if not ids:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USERS_NONE_SELECTED, scroll_y, return_section)
    rows = db.query(models.PublicUser).filter(models.PublicUser.id.in_(ids)).all()
    if not rows:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)

    action_key = action.strip().lower()
    if action_key not in PUBLIC_USER_BULK_ACTIONS:
        return _admin_redirect(ADMIN_MSG_PUBLIC_USERS_BULK_INVALID_ACTION, scroll_y, return_section)
    if action_key == "resend_verification":
        # Fast fail if SMTP settings are invalid.
        sample_ok, _ = validate_mailer_settings()
        if not sample_ok:
            return _admin_redirect(ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED, scroll_y, return_section)

    updated = 0
    queued = 0
    for row in rows:
        row_updated, row_queued = _apply_public_user_bulk_action(db, action_key, row, request)
        updated += row_updated
        queued += row_queued
    db.commit()
    log_security_event(
        "admin_public_users_bulk_action",
        request,
        "success",
        email=admin_user.email,
        details={"action": action_key, "selected": len(ids), "updated": updated, "queued": queued},
    )
    return _admin_redirect(ADMIN_MSG_PUBLIC_USERS_BULK_DONE, scroll_y, return_section)


@router.post("/admin/rooms")
def admin_create_room(
    name: str = Form(...),
    capacity: int = Form(10),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = models.Room(center_id=cid, name=name, capacity=capacity)
    db.add(room)
    db.commit()
    return _admin_redirect(ADMIN_MSG_ROOM_CREATED, scroll_y, return_section)


@router.post("/admin/rooms/update")
def admin_update_room(
    room_id: int = Form(...),
    name: str = Form(...),
    capacity: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    room = db.get(models.Room, room_id)
    if not room or room.center_id != cid:
        raise HTTPException(status_code=404, detail="Room not found")
    if capacity <= 0:
        return _admin_redirect(ADMIN_MSG_ROOM_CAPACITY_INVALID, scroll_y, return_section)
    room.name = name.strip() or room.name
    room.capacity = capacity
    db.commit()
    return _admin_redirect(ADMIN_MSG_ROOM_UPDATED, scroll_y, return_section)


@router.post("/admin/rooms/delete")
def admin_delete_room(
    room_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
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
            return _admin_redirect(ADMIN_MSG_ROOM_HAS_BOOKINGS, scroll_y, return_section)
        for session in room_sessions:
            db.delete(session)

    db.delete(room)
    db.commit()
    return _admin_redirect(ADMIN_MSG_ROOM_DELETED, scroll_y, return_section)


@router.post("/admin/rooms/delete-bulk")
def admin_delete_rooms_bulk(
    room_ids: list[int] = Form(default=[]),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    selected_ids = sorted(set(room_ids))
    if not selected_ids:
        return _admin_redirect(ADMIN_MSG_ROOMS_NONE_SELECTED, scroll_y, return_section)

    rooms = (
        db.query(models.Room)
        .filter(models.Room.center_id == cid, models.Room.id.in_(selected_ids))
        .all()
    )
    if not rooms:
        return _admin_redirect(ADMIN_MSG_ROOMS_NOT_FOUND, scroll_y, return_section)

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
        return _admin_redirect(ADMIN_MSG_ROOMS_DELETED_PARTIAL_BOOKINGS, scroll_y, return_section)
    if deleted > 0:
        return _admin_redirect(ADMIN_MSG_ROOMS_DELETED, scroll_y, return_section)
    if blocked_bookings > 0:
        return _admin_redirect(ADMIN_MSG_ROOMS_DELETE_HAS_BOOKINGS, scroll_y, return_section)
    return _admin_redirect(ADMIN_MSG_ROOMS_DELETE_BLOCKED, scroll_y, return_section)


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
    return_section: str = Form(""),
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
    return _admin_redirect(ADMIN_MSG_SESSION_CREATED, scroll_y, return_section)


@router.post("/admin/sessions/delete")
def admin_delete_session(
    session_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff", "trainer")),
):
    cid = require_user_center_id(user)
    yoga_session = db.get(models.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != cid:
        raise HTTPException(status_code=404, detail="Session not found")

    booking_ids = [b.id for b in db.query(models.Booking).filter(models.Booking.session_id == session_id).all()]
    if booking_ids:
        db.query(models.ReminderSent).filter(models.ReminderSent.booking_id.in_(booking_ids)).delete(
            synchronize_session=False
        )
        db.query(models.SessionRating).filter(models.SessionRating.booking_id.in_(booking_ids)).delete(
            synchronize_session=False
        )
        db.query(models.Payment).filter(models.Payment.booking_id.in_(booking_ids)).delete(
            synchronize_session=False
        )
    db.query(models.SessionWaitlist).filter(models.SessionWaitlist.session_id == session_id).delete(
        synchronize_session=False
    )
    db.query(models.Booking).filter(models.Booking.session_id == session_id).delete()
    db.delete(yoga_session)
    db.commit()
    return _admin_redirect(ADMIN_MSG_SESSION_DELETED, scroll_y, return_section)


@router.post("/admin/plans")
def admin_create_plan(
    name: str = Form(...),
    plan_type: str = Form(...),
    price: float = Form(...),
    session_limit: str = Form(default=""),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
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
    return _admin_redirect(ADMIN_MSG_PLAN_CREATED, scroll_y, return_section)


@router.post("/admin/plans/update-name")
def admin_update_plan_name(
    plan_id: int = Form(...),
    name: str = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")
    new_name = name.strip()
    if not new_name:
        return _admin_redirect(ADMIN_MSG_PLAN_NAME_INVALID, scroll_y, return_section)
    plan.name = new_name
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_UPDATED, scroll_y, return_section)


@router.post("/admin/plans/update-details")
def admin_update_plan_details(
    plan_id: int = Form(...),
    plan_type: str = Form(...),
    price: float = Form(...),
    session_limit: str = Form(default=""),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_type_clean = plan_type.strip().lower()
    if plan_type_clean not in ("weekly", "monthly", "yearly"):
        return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
    if price < 0:
        return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)

    parsed_session_limit = None
    if session_limit.strip():
        try:
            parsed_session_limit = int(session_limit)
        except ValueError:
            return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
        if parsed_session_limit <= 0:
            return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)

    plan.plan_type = plan_type_clean
    plan.price = float(price)
    plan.session_limit = parsed_session_limit
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_DETAILS_UPDATED, scroll_y, return_section)


@router.post("/admin/plans/delete")
def admin_delete_plan(
    plan_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != cid:
        raise HTTPException(status_code=404, detail="Plan not found")
    has_subscriptions = db.query(models.ClientSubscription).filter(models.ClientSubscription.plan_id == plan_id).first()
    if has_subscriptions:
        return _admin_redirect(ADMIN_MSG_PLAN_HAS_SUBSCRIPTIONS, scroll_y, return_section)
    db.delete(plan)
    db.commit()
    return _admin_redirect(ADMIN_MSG_PLAN_DELETED, scroll_y, return_section)


@router.post("/admin/faqs")
def admin_create_faq(
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    is_active: str = Form("1"),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    q = question.strip()
    a = answer.strip()
    if not q or not a:
        return _admin_redirect(ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
    row = models.FAQItem(
        center_id=cid,
        question=q,
        answer=a,
        sort_order=max(0, int(sort_order)),
        is_active=is_active in {"1", "true", "on", "yes"},
    )
    db.add(row)
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_CREATED, scroll_y, return_section)


@router.post("/admin/faqs/update")
def admin_update_faq(
    faq_id: int = Form(...),
    question: str = Form(...),
    answer: str = Form(...),
    sort_order: int = Form(0),
    is_active: str = Form("1"),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FAQItem, faq_id)
    if not row or row.center_id != cid:
        return _admin_redirect(ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
    q = question.strip()
    a = answer.strip()
    if not q or not a:
        return _admin_redirect(ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
    row.question = q
    row.answer = a
    row.sort_order = max(0, int(sort_order))
    row.is_active = is_active in {"1", "true", "on", "yes"}
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_UPDATED, scroll_y, return_section)


@router.post("/admin/faqs/delete")
def admin_delete_faq(
    faq_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FAQItem, faq_id)
    if not row or row.center_id != cid:
        return _admin_redirect(ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
    db.delete(row)
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_DELETED, scroll_y, return_section)


@router.post("/admin/faqs/reorder")
def admin_reorder_faqs(
    ordered_ids_csv: str = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    raw = [x.strip() for x in ordered_ids_csv.split(",") if x.strip()]
    if not raw:
        return _admin_redirect(ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
    try:
        ids = [int(x) for x in raw]
    except ValueError:
        return _admin_redirect(ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
    unique_ids = list(dict.fromkeys(ids))
    rows = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == cid, models.FAQItem.id.in_(unique_ids))
        .all()
    )
    if len(rows) != len(unique_ids):
        return _admin_redirect(ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
    row_by_id = {r.id: r for r in rows}
    for idx, faq_id in enumerate(unique_ids, start=1):
        row_by_id[faq_id].sort_order = idx
    db.commit()
    return _admin_redirect(ADMIN_MSG_FAQ_REORDERED, scroll_y, return_section)


def _optional_non_negative_int_form(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = int(s)
    except ValueError:
        raise ValueError("nan")
    if v < 0:
        raise ValueError("neg")
    return v


@router.post("/admin/center/loyalty")
def admin_center_loyalty(
    request: Request,
    loyalty_bronze_min: str = Form(""),
    loyalty_silver_min: str = Form(""),
    loyalty_gold_min: str = Form(""),
    loyalty_label_bronze: str = Form(""),
    loyalty_label_silver: str = Form(""),
    loyalty_label_gold: str = Form(""),
    loyalty_reward_bronze: str = Form(""),
    loyalty_reward_silver: str = Form(""),
    loyalty_reward_gold: str = Form(""),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    if not center:
        return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, scroll_y, return_section)
    try:
        pb = _optional_non_negative_int_form(loyalty_bronze_min)
        ps = _optional_non_negative_int_form(loyalty_silver_min)
        pg = _optional_non_negative_int_form(loyalty_gold_min)
    except ValueError:
        return _admin_redirect(ADMIN_MSG_CENTER_LOYALTY_BAD_NUMBER, scroll_y, return_section)

    prospective = models.Center()
    prospective.loyalty_bronze_min = pb
    prospective.loyalty_silver_min = ps
    prospective.loyalty_gold_min = pg
    b, s, g = effective_loyalty_thresholds(prospective)
    err = validate_loyalty_threshold_triple(b, s, g)
    if err:
        return _admin_redirect(ADMIN_MSG_CENTER_LOYALTY_INVALID, scroll_y, return_section)

    def _lbl(x: str) -> str | None:
        t = (x or "").strip()[:64]
        return t or None

    def _reward(x: str) -> str | None:
        t = (x or "").strip()[:LOYALTY_REWARD_MAX_LEN]
        return t or None

    center.loyalty_bronze_min = pb
    center.loyalty_silver_min = ps
    center.loyalty_gold_min = pg
    center.loyalty_label_bronze = _lbl(loyalty_label_bronze)
    center.loyalty_label_silver = _lbl(loyalty_label_silver)
    center.loyalty_label_gold = _lbl(loyalty_label_gold)
    center.loyalty_reward_bronze = _reward(loyalty_reward_bronze)
    center.loyalty_reward_silver = _reward(loyalty_reward_silver)
    center.loyalty_reward_gold = _reward(loyalty_reward_gold)
    db.commit()
    log_security_event(
        "admin_center_loyalty",
        request,
        "success",
        email=user.email,
        details={"center_id": cid, "thresholds": [b, s, g]},
    )
    return _admin_redirect(ADMIN_MSG_CENTER_LOYALTY_SAVED, scroll_y, return_section)


@router.post("/admin/center/branding")
async def admin_center_branding(
    brand_tagline: str = Form(""),
    remove_logo: str = Form(""),
    remove_hero: str = Form(""),
    restore_hero_stock: str = Form(""),
    hero_gradient_only: str = Form(""),
    logo: UploadFile | None = File(default=None),
    hero: UploadFile | None = File(default=None),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    center = db.get(models.Center, cid)
    if not center:
        return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, scroll_y, return_section)
    had_custom_hero = bool(center.hero_image_url)

    logo_raw = (logo.filename or "").strip() if logo else ""
    logo_ext: str | None = None
    logo_bytes: bytes | None = None
    if logo and logo_raw:
        ext = logo_raw.rsplit(".", 1)[-1].lower() if "." in logo_raw else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        body = await logo.read()
        if not body or len(body) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        logo_ext = ext
        logo_bytes = body

    hero_raw = (hero.filename or "").strip() if hero else ""
    hero_ext: str | None = None
    hero_bytes: bytes | None = None
    if hero and hero_raw:
        ext = hero_raw.rsplit(".", 1)[-1].lower() if "." in hero_raw else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        body = await hero.read()
        if not body or len(body) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
        hero_ext = ext
        hero_bytes = body

    tag = brand_tagline.strip()[:500]
    center.brand_tagline = tag if tag else None

    remove = _is_truthy_env(remove_logo)
    remove_h = _is_truthy_env(remove_hero)
    restore_stock = _is_truthy_env(restore_hero_stock)
    gradient_only = _is_truthy_env(hero_gradient_only)

    if logo_ext is not None and logo_bytes is not None:
        CENTER_LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _unlink_center_uploads(f"center_{cid}.*")
        dest = CENTER_LOGO_UPLOAD_DIR / f"center_{cid}.{logo_ext}"
        dest.write_bytes(logo_bytes)
        center.logo_url = f"/static/uploads/centers/center_{cid}.{logo_ext}"
    elif remove:
        _unlink_center_uploads(f"center_{cid}.*")
        center.logo_url = None

    if restore_stock:
        _unlink_center_uploads(f"center_{cid}_hero.*")
        center.hero_image_url = None
        center.hero_show_stock_photo = True
    elif hero_ext is not None and hero_bytes is not None:
        CENTER_LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        _unlink_center_uploads(f"center_{cid}_hero.*")
        dest = CENTER_LOGO_UPLOAD_DIR / f"center_{cid}_hero.{hero_ext}"
        dest.write_bytes(hero_bytes)
        center.hero_image_url = f"/static/uploads/centers/center_{cid}_hero.{hero_ext}"
        center.hero_show_stock_photo = False
    elif remove_h:
        _unlink_center_uploads(f"center_{cid}_hero.*")
        center.hero_image_url = None
        center.hero_show_stock_photo = False
    elif gradient_only and not had_custom_hero:
        center.hero_show_stock_photo = False

    db.commit()
    return _admin_redirect(ADMIN_MSG_CENTER_BRANDING_UPDATED, scroll_y, return_section)


@router.post("/admin/center/posts/save")
async def admin_save_center_post(
    request: Request,
    title: str = Form(...),
    post_type: str = Form(...),
    summary: str = Form(""),
    body: str = Form(""),
    post_id: str = Form(""),
    is_pinned: str = Form(""),
    is_published: str = Form(""),
    remove_cover: str = Form(""),
    remove_image_ids: str = Form(""),
    cover_remote_url: str = Form(""),
    gallery_remote_urls: str = Form(""),
    cover: UploadFile | None = File(None),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    ptype = (post_type or "").strip().lower()
    if ptype not in CENTER_POST_TYPES:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
    ttl = (title or "").strip()
    if not ttl or len(ttl) > 220:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
    summ = (summary or "").strip()[:600]
    bod = (body or "").strip()
    if len(bod) > CENTER_POST_MAX_BODY_CHARS:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)

    pid = 0
    if (post_id or "").strip().isdigit():
        pid = int(post_id.strip())
    row: models.CenterPost | None = None
    if pid:
        row = db.get(models.CenterPost, pid)
        if not row or row.center_id != cid:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_NOT_FOUND, scroll_y, return_section)
    else:
        row = models.CenterPost(center_id=cid, post_type=ptype, title=ttl)
        db.add(row)
        db.flush()

    row.post_type = ptype
    row.title = ttl
    row.summary = summ if summ else None
    row.body = bod if bod else None
    row.is_pinned = _is_truthy_env(is_pinned)
    row.is_published = _is_truthy_env(is_published)
    if row.is_published and row.published_at is None:
        row.published_at = utcnow_naive()
    row.updated_at = utcnow_naive()

    if row.is_pinned:
        db.query(models.CenterPost).filter(
            models.CenterPost.center_id == cid,
            models.CenterPost.id != row.id,
        ).update({models.CenterPost.is_pinned: False})

    if _is_truthy_env(remove_cover) and row.cover_image_url:
        _unlink_static_url_file(row.cover_image_url)
        row.cover_image_url = None

    cover_raw = (cover.filename or "").strip() if cover else ""
    if cover and cover_raw:
        ext = cover_raw.rsplit(".", 1)[-1].lower() if "." in cover_raw else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        cbody = await cover.read()
        if not cbody or len(cbody) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        if row.cover_image_url:
            _unlink_static_url_file(row.cover_image_url)
        CENTER_POST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = CENTER_POST_UPLOAD_DIR / f"center_{cid}_post_{row.id}_cover.{ext}"
        dest.write_bytes(cbody)
        row.cover_image_url = f"/static/uploads/centers/posts/{dest.name}"

    cover_remote_raw = (cover_remote_url or "").strip()
    if cover_remote_raw and not (cover and cover_raw):
        sanitized_remote = _sanitize_center_post_remote_image_url(cover_remote_raw)
        if not sanitized_remote:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        if row.cover_image_url and row.cover_image_url != sanitized_remote:
            _unlink_static_url_file(row.cover_image_url)
        row.cover_image_url = sanitized_remote

    for part in (remove_image_ids or "").replace(" ", "").split(","):
        if not part.isdigit():
            continue
        img_id = int(part)
        img_row = db.get(models.CenterPostImage, img_id)
        if not img_row or img_row.post_id != row.id:
            continue
        _unlink_static_url_file(img_row.image_url)
        db.delete(img_row)

    form = await request.form()
    gallery_files = [
        f
        for f in form.getlist("gallery")
        if hasattr(f, "filename") and (getattr(f, "filename", None) or "").strip()
    ]
    current_n = (
        db.query(models.CenterPostImage)
        .filter(models.CenterPostImage.post_id == row.id)
        .count()
    )
    max_sort = (
        db.query(func.coalesce(func.max(models.CenterPostImage.sort_order), 0))
        .filter(models.CenterPostImage.post_id == row.id)
        .scalar()
    )
    next_order = int(max_sort or 0)

    for gf in gallery_files:
        if current_n >= CENTER_POST_MAX_GALLERY:
            break
        gname = (gf.filename or "").strip()
        ext = gname.rsplit(".", 1)[-1].lower() if "." in gname else ""
        if ext not in CENTER_LOGO_ALLOWED_EXT:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        gbody = await gf.read()
        if not gbody or len(gbody) > CENTER_LOGO_MAX_BYTES:
            return _admin_redirect(ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        next_order += 1
        CENTER_POST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = CENTER_POST_UPLOAD_DIR / f"center_{cid}_post_{row.id}_gallery_{next_order}_{utcnow_naive().timestamp():.0f}.{ext}"
        dest.write_bytes(gbody)
        db.add(
            models.CenterPostImage(
                post_id=row.id,
                image_url=f"/static/uploads/centers/posts/{dest.name}",
                sort_order=next_order,
            )
        )
        current_n += 1

    for remote_g in _parse_center_post_gallery_remote_urls(gallery_remote_urls):
        if current_n >= CENTER_POST_MAX_GALLERY:
            break
        next_order += 1
        db.add(
            models.CenterPostImage(
                post_id=row.id,
                image_url=remote_g,
                sort_order=next_order,
            )
        )
        current_n += 1

    db.commit()
    return _admin_redirect(ADMIN_MSG_CENTER_POST_SAVED, scroll_y, return_section)


@router.post("/admin/center/posts/delete")
def admin_delete_center_post(
    post_id: int = Form(...),
    scroll_y: str = Form(default=""),
    return_section: str = Form(""),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles_cookie_or_bearer("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.CenterPost, post_id)
    if not row or row.center_id != cid:
        return _admin_redirect(ADMIN_MSG_CENTER_POST_NOT_FOUND, scroll_y, return_section)
    _delete_center_post_disk_files(cid, row.id)
    db.delete(row)
    db.commit()
    return _admin_redirect(ADMIN_MSG_CENTER_POST_DELETED, scroll_y, return_section)



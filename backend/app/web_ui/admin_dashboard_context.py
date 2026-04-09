"""Build template context for the admin dashboard (GET /admin)."""

from __future__ import annotations

from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks import (
    aggregate_paid_revenue_and_public_user_stats,
    build_ops_rows_and_schedule_conflicts,
    build_revenue_7d_bars,
    fetch_admin_kpi_counts,
    fetch_admin_login_audit_rows,
    load_security_audit_bundle,
    normalize_admin_list_page,
)


def build_admin_dashboard_template_context(
    *,
    db: _s.Session,
    user: _s.models.User,
    msg: str | None,
    room_sort: str,
    public_user_q: str,
    public_user_status: str,
    public_user_verified: str,
    public_user_page: int,
    trash_page: int,
    trash_q: str,
    sessions_page: int,
    payments_page: int,
    audit_event_type: str,
    audit_status: str,
    audit_email: str,
    audit_ip: str,
    audit_page: int,
    payment_date_from: str,
    payment_date_to: str,
    post_edit: int,
    center_posts_page: int,
) -> dict[str, Any]:
    """Load rooms, users, payments, security, posts, and aggregate KPIs for admin.html."""
    cid = _s.require_user_center_id(user)
    center = db.get(_s.models.Center, cid)
    if center:
        if center.name == _s.DEMO_CENTER_NAME:
            _s.ensure_demo_news_posts(db, center.id)
        _s._clear_center_branding_urls_if_files_missing(db, center)
    room_sort_key = (room_sort or "id_asc").strip().lower()
    room_ordering = {
        "id_asc": (_s.models.Room.id.asc(),),
        "name": (_s.models.Room.name.asc(), _s.models.Room.id.asc()),
        "newest": (_s.models.Room.id.desc(),),
        "capacity_desc": (_s.models.Room.capacity.desc(), _s.models.Room.name.asc(), _s.models.Room.id.asc()),
        "capacity_asc": (_s.models.Room.capacity.asc(), _s.models.Room.name.asc(), _s.models.Room.id.asc()),
    }
    if room_sort_key in {"sessions_desc", "sessions_asc"}:
        session_count_order = (
            _s.func.count(_s.models.YogaSession.id).desc()
            if room_sort_key == "sessions_desc"
            else _s.func.count(_s.models.YogaSession.id).asc()
        )
        rooms = (
            db.query(_s.models.Room)
            .outerjoin(
                _s.models.YogaSession,
                _s.and_(
                    _s.models.YogaSession.room_id == _s.models.Room.id,
                    _s.models.YogaSession.center_id == cid,
                ),
            )
            .filter(_s.models.Room.center_id == cid)
            .group_by(_s.models.Room.id)
            .order_by(session_count_order, _s.models.Room.name.asc(), _s.models.Room.id.asc())
            .all()
        )
    else:
        room_order_by = room_ordering.get(room_sort_key, room_ordering["id_asc"])
        rooms = (
            db.query(_s.models.Room)
            .filter(_s.models.Room.center_id == cid)
            .order_by(*room_order_by)
            .all()
        )
    plans = (
        db.query(_s.models.SubscriptionPlan)
        .filter(_s.models.SubscriptionPlan.center_id == cid)
        .order_by(_s.models.SubscriptionPlan.price.asc())
        .all()
    )
    rooms_by_id = {r.id: r for r in rooms}

    sessions_page_size = _s.ADMIN_SESSIONS_PAGE_SIZE
    sessions_base_query = db.query(_s.models.YogaSession).filter(_s.models.YogaSession.center_id == cid)
    sessions_total = sessions_base_query.order_by(None).count()
    safe_sessions_page, sessions_total_pages, sessions_offset = normalize_admin_list_page(
        sessions_page,
        sessions_total,
        sessions_page_size,
    )
    sessions = (
        sessions_base_query.order_by(_s.models.YogaSession.starts_at.desc())
        .offset(sessions_offset)
        .limit(sessions_page_size)
        .all()
    )
    session_ids_page = [int(s.id) for s in sessions]
    spots_by_session_page = _s._spots_available_map(db, cid, session_ids_page)
    faqs = (
        db.query(_s.models.FAQItem)
        .filter(_s.models.FAQItem.center_id == cid)
        .order_by(_s.models.FAQItem.sort_order.asc(), _s.models.FAQItem.created_at.asc())
        .all()
    )
    public_users_query = _s._public_users_query_for_center(db, cid)
    q = public_user_q.strip()
    if q:
        public_users_query = public_users_query.filter(
            _s.or_(
                _s.models.PublicUser.full_name.ilike(f"%{q}%"),
                _s.models.PublicUser.email.ilike(f"%{q}%"),
                _s.models.PublicUser.phone.ilike(f"%{q}%"),
            )
        )
    status_key = public_user_status.strip().lower() or "active"
    if status_key == "deleted":
        public_users_query = public_users_query.filter(_s.models.PublicUser.is_deleted.is_(True))
    elif status_key == "inactive":
        public_users_query = public_users_query.filter(
            _s.models.PublicUser.is_deleted.is_(False), _s.models.PublicUser.is_active.is_(False)
        )
    else:
        public_users_query = public_users_query.filter(
            _s.models.PublicUser.is_deleted.is_(False), _s.models.PublicUser.is_active.is_(True)
        )
    verified_key = public_user_verified.strip().lower()
    if verified_key == "verified":
        public_users_query = public_users_query.filter(_s.models.PublicUser.email_verified.is_(True))
    elif verified_key == "unverified":
        public_users_query = public_users_query.filter(_s.models.PublicUser.email_verified.is_(False))
    public_users_page_size = _s.ADMIN_PUBLIC_USERS_PAGE_SIZE
    public_users_total = public_users_query.order_by(None).count()
    safe_public_user_page, public_users_total_pages, public_users_offset = normalize_admin_list_page(
        public_user_page,
        public_users_total,
        public_users_page_size,
    )
    public_users = (
        public_users_query.order_by(_s.models.PublicUser.created_at.desc())
        .offset(public_users_offset)
        .limit(public_users_page_size)
        .all()
    )
    trash_q_s = trash_q.strip()
    trash_base = _s._public_users_query_for_center(db, cid).filter(_s.models.PublicUser.is_deleted.is_(True))
    if trash_q_s:
        trash_base = trash_base.filter(
            _s.or_(
                _s.models.PublicUser.full_name.ilike(f"%{trash_q_s}%"),
                _s.models.PublicUser.email.ilike(f"%{trash_q_s}%"),
            )
        )
    trash_total = trash_base.order_by(None).count()
    safe_trash_page, trash_total_pages, trash_offset = normalize_admin_list_page(
        trash_page,
        trash_total,
        public_users_page_size,
    )
    trash_users_list = (
        trash_base.order_by(_s.models.PublicUser.deleted_at.desc(), _s.models.PublicUser.id.desc())
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
    now_for_sessions = _s.utcnow_naive()
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
                "starts_at_display": _s._fmt_dt(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "room_id": s.room_id,
                "spots_available": spots_by_session_page.get(int(s.id), 0),
                "capacity": room.capacity if room else 0,
                "is_past": bool(s.starts_at < now_for_sessions),
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

    today = _s.utcnow_naive().date()
    tomorrow_d = today + _s.timedelta(days=1)
    now_na = _s.utcnow_naive()
    payment_from_dt = _s._parse_optional_date_str(payment_date_from)
    payment_to_dt = _s._parse_optional_date_str(payment_date_to)

    kpi = fetch_admin_kpi_counts(db, cid, today, now_na)
    sessions_today_no_bookings = kpi.sessions_today_no_bookings
    subs_expiring_7d = kpi.subs_expiring_7d
    pending_payments_stale_8d = kpi.pending_payments_stale_8d
    failed_payments_7d = kpi.failed_payments_7d
    sessions_scheduled_today = kpi.sessions_scheduled_today
    bookings_active_today = kpi.bookings_active_today
    public_users_unverified_count = kpi.public_users_unverified_count

    revenue_7d_bars = build_revenue_7d_bars(db, cid, today)

    ops_today_rows, ops_tomorrow_rows, schedule_conflicts = build_ops_rows_and_schedule_conflicts(
        db, cid, rooms_by_id, today, tomorrow_d, now_na
    )

    admin_login_audit_rows = fetch_admin_login_audit_rows(db)

    paid_revenue_total, paid_revenue_today, public_users_count, public_users_deleted_count, public_users_new_7d = (
        aggregate_paid_revenue_and_public_user_stats(db, cid, today)
    )
    dashboard = {
        "rooms_count": len(rooms),
        "sessions_count": sessions_total,
        "bookings_count": db.query(_s.models.Booking).filter(_s.models.Booking.center_id == cid).count(),
        "clients_count": db.query(_s.models.Client).filter(_s.models.Client.center_id == cid).count(),
        "active_plans_count": sum(1 for p in plans if p.is_active),
        "active_subscriptions_count": (
            db.query(_s.models.ClientSubscription)
            .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
            .filter(
                _s.models.Client.center_id == cid,
                _s.models.ClientSubscription.status == "active",
            )
            .count()
        ),
        "revenue_total": float(paid_revenue_total or 0.0),
        "revenue_today": float(paid_revenue_today or 0.0),
        "public_users_count": int(public_users_count) - int(public_users_deleted_count),
        "public_users_deleted_count": int(public_users_deleted_count),
        "public_users_new_7d": int(public_users_new_7d),
    }
    payments_page_size = _s.ADMIN_PAYMENTS_PAGE_SIZE
    payments_base_query = db.query(_s.models.Payment).filter(_s.models.Payment.center_id == cid)
    if payment_from_dt:
        payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) >= payment_from_dt)
    if payment_to_dt:
        payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) <= payment_to_dt)
    payments_total = payments_base_query.order_by(None).count()
    safe_payments_page, payments_total_pages, payments_offset = normalize_admin_list_page(
        payments_page,
        payments_total,
        payments_page_size,
    )
    recent_payments = (
        payments_base_query.order_by(_s.models.Payment.paid_at.desc())
        .offset(payments_offset)
        .limit(payments_page_size)
        .all()
    )
    client_ids = [p.client_id for p in recent_payments]
    clients_by_id = {
        c.id: c
        for c in db.query(_s.models.Client).filter(_s.models.Client.id.in_(client_ids)).all()
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
                "paid_at_display": _s._fmt_dt(pay.paid_at),
            }
        )
    loyalty_by_email = _s.loyalty_confirmed_counts_by_email_lower(db, cid)
    public_user_rows = []
    for u in public_users:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = _s.loyalty_context_for_count(cnt, center=center)
        public_user_rows.append(
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": _s._phone_admin_display(u.phone),
                "is_active": u.is_active,
                "email_verified": u.email_verified,
                "is_deleted": bool(u.is_deleted),
                "created_at_display": _s._fmt_dt(u.created_at),
                "loyalty_confirmed_count": cnt,
                "loyalty_tier": lt["loyalty_tier"],
                "loyalty_tier_label": lt["loyalty_tier_label"],
            }
        )
    trash_user_rows = []
    for u in trash_users_list:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = _s.loyalty_context_for_count(cnt, center=center)
        trash_user_rows.append(
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": _s._phone_admin_display(u.phone),
                "deleted_at_display": _s._fmt_dt(u.deleted_at),
                "created_at_display": _s._fmt_dt(u.created_at),
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

    sec = load_security_audit_bundle(
        db,
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
        audit_page=audit_page,
    )
    security_event_rows = sec.security_event_rows
    security_summary = sec.security_summary
    block_history_rows = sec.block_history_rows
    security_export_url = sec.security_export_url
    safe_audit_page = sec.safe_audit_page
    security_events_total = sec.security_events_total
    security_events_total_pages = sec.security_events_total_pages
    audit_page_size = sec.audit_page_size
    admin_flash = None
    if msg:
        flash_data = _s.ADMIN_FLASH_MESSAGES.get(msg)
        if flash_data:
            text, level = flash_data
            admin_flash = {"text": text, "level": level}

    base_admin_params = {
        _s.ADMIN_QP_ROOM_SORT: room_sort,
        _s.ADMIN_QP_PUBLIC_USER_Q: public_user_q,
        _s.ADMIN_QP_PUBLIC_USER_STATUS: public_user_status,
        _s.ADMIN_QP_PUBLIC_USER_VERIFIED: public_user_verified,
        _s.ADMIN_QP_PUBLIC_USER_PAGE: str(safe_public_user_page),
        _s.ADMIN_QP_TRASH_PAGE: str(safe_trash_page),
        _s.ADMIN_QP_TRASH_Q: trash_q,
        _s.ADMIN_QP_SESSIONS_PAGE: str(safe_sessions_page),
        _s.ADMIN_QP_PAYMENTS_PAGE: str(safe_payments_page),
        _s.ADMIN_QP_AUDIT_EVENT_TYPE: audit_event_type,
        _s.ADMIN_QP_AUDIT_STATUS: audit_status,
        _s.ADMIN_QP_AUDIT_EMAIL: audit_email,
        _s.ADMIN_QP_AUDIT_IP: audit_ip,
        _s.ADMIN_QP_AUDIT_PAGE: str(safe_audit_page),
        _s.ADMIN_QP_PAYMENT_DATE_FROM: (payment_date_from or "").strip()[:32],
        _s.ADMIN_QP_PAYMENT_DATE_TO: (payment_date_to or "").strip()[:32],
        "center_posts_page": str(max(1, int(center_posts_page or 1))),
    }

    def _admin_page_url(**overrides: str) -> str:
        params = dict(base_admin_params)
        for k, v in overrides.items():
            params[k] = v
        return _s._url_with_params("/admin", **params)

    public_users_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_PUBLIC_USER_PAGE: str(max(1, safe_public_user_page - 1))})
    public_users_page_next_url = _admin_page_url(
        **{_s.ADMIN_QP_PUBLIC_USER_PAGE: str(min(public_users_total_pages, safe_public_user_page + 1))}
    )
    security_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_AUDIT_PAGE: str(max(1, safe_audit_page - 1))})
    security_page_next_url = _admin_page_url(
        **{_s.ADMIN_QP_AUDIT_PAGE: str(min(security_events_total_pages, safe_audit_page + 1))}
    )
    sessions_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_SESSIONS_PAGE: str(max(1, safe_sessions_page - 1))})
    sessions_page_next_url = _admin_page_url(
        **{_s.ADMIN_QP_SESSIONS_PAGE: str(min(sessions_total_pages, safe_sessions_page + 1))}
    )
    payments_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_PAYMENTS_PAGE: str(max(1, safe_payments_page - 1))})
    payments_page_next_url = _admin_page_url(
        **{_s.ADMIN_QP_PAYMENTS_PAGE: str(min(payments_total_pages, safe_payments_page + 1))}
    )
    trash_page_prev_url = _admin_page_url(**{_s.ADMIN_QP_TRASH_PAGE: str(max(1, safe_trash_page - 1))})
    trash_page_next_url = _admin_page_url(
        **{_s.ADMIN_QP_TRASH_PAGE: str(min(trash_total_pages, safe_trash_page + 1))}
    )

    safe_post_edit = max(0, int(post_edit or 0))
    center_posts_page_size = _s.ADMIN_CENTER_POSTS_PAGE_SIZE
    center_posts_base_query = (
        db.query(_s.models.CenterPost)
        .filter(_s.models.CenterPost.center_id == cid)
        .order_by(_s.models.CenterPost.updated_at.desc())
    )
    center_posts_total = center_posts_base_query.order_by(None).count()
    safe_center_posts_page, center_posts_total_pages, center_posts_offset = normalize_admin_list_page(
        center_posts_page,
        center_posts_total,
        center_posts_page_size,
    )
    center_posts_all = (
        center_posts_base_query
        .offset(center_posts_offset)
        .limit(center_posts_page_size)
        .all()
    )
    center_posts_page_prev_url = _admin_page_url(
        **{"center_posts_page": str(max(1, safe_center_posts_page - 1))}
    )
    center_posts_page_next_url = _admin_page_url(
        **{"center_posts_page": str(min(center_posts_total_pages, safe_center_posts_page + 1))}
    )
    center_post_ids_page = [int(cp.id) for cp in center_posts_all]
    center_post_gallery_counts = {
        int(pid): int(cnt)
        for pid, cnt in (
            db.query(_s.models.CenterPostImage.post_id, _s.func.count(_s.models.CenterPostImage.id))
            .filter(_s.models.CenterPostImage.post_id.in_(center_post_ids_page))
            .group_by(_s.models.CenterPostImage.post_id)
            .all()
        )
    } if center_post_ids_page else {}

    def _post_admin_edit_url(edit_id: int) -> str:
        return _admin_page_url(**{_s.ADMIN_QP_POST_EDIT: str(edit_id)}) + "#section-center-posts"

    center_post_admin_rows: list[dict[str, str | int | bool]] = []
    for cp in center_posts_all:
        center_post_admin_rows.append(
            {
                "id": cp.id,
                "title": cp.title,
                "post_type": cp.post_type,
                "type_label": _s.CENTER_POST_TYPE_LABELS.get(cp.post_type, cp.post_type),
                "is_published": cp.is_published,
                "is_pinned": cp.is_pinned,
                "updated_display": _s._fmt_dt(cp.updated_at),
                "gallery_count": center_post_gallery_counts.get(int(cp.id), 0),
                "public_url": _s._url_with_params("/post", center_id=str(cid), post_id=str(cp.id))
                if cp.is_published
                else "",
                "edit_url": _post_admin_edit_url(cp.id),
            }
        )

    editing_post: dict[str, _s.Any] | None = None
    if safe_post_edit:
        ep = db.get(_s.models.CenterPost, safe_post_edit)
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
        {"value": k, "label": v} for k, v in sorted(_s.CENTER_POST_TYPE_LABELS.items(), key=lambda x: x[1])
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
    if pending_payments_stale_8d:
        admin_insights.append(
            {
                "label": f"معلّقات قديمة (+8 أيام): {pending_payments_stale_8d}",
                "href": "/admin/reports/health",
                "kind": "warn",
            }
        )
    if failed_payments_7d:
        admin_insights.append(
            {
                "label": f"مدفوعات فاشلة في آخر 7 أيام: {failed_payments_7d}",
                "href": "/admin/reports/health",
                "kind": "warn",
            }
        )

    morning_brief = {
        "sessions_today": sessions_scheduled_today,
        "bookings_today": bookings_active_today,
        "revenue_today": float(paid_revenue_today or 0),
        "pending_stale_8d": pending_payments_stale_8d,
        "failed_7d": failed_payments_7d,
        "subs_expiring_7d": subs_expiring_7d,
    }

    export_pay_params: dict[str, str] = {}
    pf = (payment_date_from or "").strip()[:32]
    pt = (payment_date_to or "").strip()[:32]
    if pf:
        export_pay_params[_s.ADMIN_QP_PAYMENT_DATE_FROM] = pf
    if pt:
        export_pay_params[_s.ADMIN_QP_PAYMENT_DATE_TO] = pt
    data_export_urls = {
        "clients": "/admin/export/clients.csv",
        "bookings": "/admin/export/bookings.csv",
        "payments": _s._url_with_params("/admin/export/payments.csv", **export_pay_params)
        if export_pay_params
        else "/admin/export/payments.csv",
    }

    _env_b, _env_s, _env_g = _s.loyalty_thresholds()
    _eff_b, _eff_s, _eff_g = _s.effective_loyalty_thresholds(center)
    loyalty_admin = {
        "env": {"bronze": _env_b, "silver": _env_s, "gold": _env_g},
        "effective": {"bronze": _eff_b, "silver": _eff_s, "gold": _eff_g},
    }

    index_page_cfg = _s.merge_index_page_config(center) if center else _s._default_index_page_config()


    return {
        "user": user,
        "center": center,
        "index_page": index_page_cfg,
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
        "center_posts_pagination": {
            "page": safe_center_posts_page,
            "page_size": center_posts_page_size,
            "total": center_posts_total,
            "total_pages": center_posts_total_pages,
            "has_prev": safe_center_posts_page > 1,
            "has_next": safe_center_posts_page < center_posts_total_pages,
            "prev_url": center_posts_page_prev_url,
            "next_url": center_posts_page_next_url,
        },
        "room_filters": {
            "sort": (
                room_sort_key
                if room_sort_key in room_ordering or room_sort_key in {"sessions_desc", "sessions_asc"}
                else "id_asc"
            ),
        },
        "center_id": cid,
        "admin_public_index_url": _s._url_with_params("/index", center_id=str(cid)),
        "admin_insights": admin_insights,
        "morning_brief": morning_brief,
        "revenue_7d_bars": revenue_7d_bars,
        "ops_today_rows": ops_today_rows,
        "ops_tomorrow_rows": ops_tomorrow_rows,
        "schedule_conflicts": schedule_conflicts,
        "admin_login_audit_rows": admin_login_audit_rows,
        "data_export_urls": data_export_urls,
        "payment_date_from_value": pf,
        "payment_date_to_value": pt,
        "loyalty_admin": loyalty_admin,
        **_s.admin_ui_flags(user),
        "permission_catalog": _s.PERMISSION_CATALOG,
        "assignable_staff_roles": tuple(
            r for r in _s.STAFF_ROLE_CATALOG if r["id"] in _s.ASSIGNABLE_BY_CENTER_OWNER
        ),
        "staff_role_sections_hints_json": _s.json.dumps(_s.STAFF_ROLE_UI_SECTIONS_HINT, ensure_ascii=False),
        "staff_permission_groups": _s.permission_catalog_grouped_for_custom_staff(),
        "role_permission_matrix": _s.handbook_matrix_rows(),
        "center_post_admin_rows": center_post_admin_rows,
        "editing_post": editing_post,
        "center_post_type_choices": center_post_type_choices,
        "post_edit_id": safe_post_edit,
        "perm_report_sessions": (
            _s.user_has_permission(user, "sessions.manage")
            or _s.user_has_permission(user, "reports.financial")
            or _s.user_has_permission(user, "dashboard.view")
        ),
        "perm_report_revenue": (
            _s.user_has_permission(user, "payments.records")
            or _s.user_has_permission(user, "reports.financial")
            or _s.user_has_permission(user, "dashboard.financial")
        ),
    }

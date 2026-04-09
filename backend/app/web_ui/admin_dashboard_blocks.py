"""Query and small-build helpers for the admin dashboard (used by admin_dashboard_context)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from . import impl_state as _s

_SESSION_LEVEL_LABELS = {
    "beginner": "مبتدئ",
    "intermediate": "متوسط",
    "advanced": "متقدم",
}
_PLAN_TYPE_LABELS = {
    "weekly": "أسبوعي",
    "monthly": "شهري",
    "yearly": "سنوي",
}


def normalize_admin_list_page(page_value: int, total_items: int, page_size: int) -> tuple[int, int, int]:
    safe_page = max(1, int(page_value or 1))
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    if safe_page > total_pages:
        safe_page = total_pages
    offset = (safe_page - 1) * page_size
    return safe_page, total_pages, offset


@dataclass(frozen=True)
class AdminKpiCounts:
    sessions_today_no_bookings: int
    subs_expiring_7d: int
    pending_payments_stale_8d: int
    failed_payments_7d: int
    sessions_scheduled_today: int
    bookings_active_today: int
    public_users_unverified_count: int


def fetch_admin_kpi_counts(db: _s.Session, cid: int, today: Any, now_na: Any) -> AdminKpiCounts:
    sessions_today_no_bookings = (
        db.query(_s.models.YogaSession.id)
        .outerjoin(
            _s.models.Booking,
            _s.and_(
                _s.models.Booking.session_id == _s.models.YogaSession.id,
                _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
            ),
        )
        .filter(
            _s.models.YogaSession.center_id == cid,
            _s.func.date(_s.models.YogaSession.starts_at) == today,
        )
        .group_by(_s.models.YogaSession.id)
        .having(_s.func.count(_s.models.Booking.id) == 0)
        .count()
    )
    subs_expiring_7d = (
        db.query(_s.models.ClientSubscription)
        .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
        .filter(
            _s.models.Client.center_id == cid,
            _s.models.ClientSubscription.status == "active",
            _s.models.ClientSubscription.end_date >= now_na,
            _s.models.ClientSubscription.end_date <= now_na + _s.timedelta(days=7),
        )
        .count()
    )
    pending_cutoff = now_na - _s.timedelta(days=8)
    pending_payments_stale_8d = int(
        db.query(_s.func.count(_s.models.Payment.id))
        .filter(
            _s.models.Payment.center_id == cid,
            _s.models.Payment.status.in_(("pending", "pending_payment")),
            _s.func.coalesce(_s.models.Payment.created_at, _s.models.Payment.paid_at) <= pending_cutoff,
        )
        .scalar()
        or 0
    )
    failed_payments_7d = int(
        db.query(_s.func.count(_s.models.Payment.id))
        .filter(
            _s.models.Payment.center_id == cid,
            _s.models.Payment.status == "failed",
            _s.func.date(_s.models.Payment.paid_at) >= today - _s.timedelta(days=7),
            _s.func.date(_s.models.Payment.paid_at) <= today,
        )
        .scalar()
        or 0
    )
    sessions_scheduled_today = int(
        db.query(_s.func.count(_s.models.YogaSession.id))
        .filter(_s.models.YogaSession.center_id == cid, _s.func.date(_s.models.YogaSession.starts_at) == today)
        .scalar()
        or 0
    )
    bookings_active_today = int(
        db.query(_s.func.count(_s.models.Booking.id))
        .join(_s.models.YogaSession, _s.models.YogaSession.id == _s.models.Booking.session_id)
        .filter(
            _s.models.YogaSession.center_id == cid,
            _s.func.date(_s.models.YogaSession.starts_at) == today,
            _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
        )
        .scalar()
        or 0
    )
    public_users_unverified_count = (
        _s._public_users_query_for_center(db, cid)
        .filter(
            _s.models.PublicUser.is_deleted.is_(False),
            _s.models.PublicUser.is_active.is_(True),
            _s.models.PublicUser.email_verified.is_(False),
        )
        .count()
    )
    return AdminKpiCounts(
        sessions_today_no_bookings=sessions_today_no_bookings,
        subs_expiring_7d=subs_expiring_7d,
        pending_payments_stale_8d=pending_payments_stale_8d,
        failed_payments_7d=failed_payments_7d,
        sessions_scheduled_today=sessions_scheduled_today,
        bookings_active_today=bookings_active_today,
        public_users_unverified_count=public_users_unverified_count,
    )


def build_revenue_7d_bars(db: _s.Session, cid: int, today: Any) -> list[dict[str, Any]]:
    revenue_7d_bars: list[dict[str, Any]] = []
    max_rev_7d = 0.01
    rev_start = today - _s.timedelta(days=6)
    revenue_7d_rows = (
        db.query(
            _s.func.date(_s.models.Payment.paid_at).label("day"),
            _s.func.coalesce(_s.func.sum(_s.models.Payment.amount), 0.0),
        )
        .filter(
            _s.models.Payment.center_id == cid,
            _s.models.Payment.status == "paid",
            _s.func.date(_s.models.Payment.paid_at) >= rev_start,
            _s.func.date(_s.models.Payment.paid_at) <= today,
        )
        .group_by(_s.func.date(_s.models.Payment.paid_at))
        .all()
    )
    revenue_by_day = {str(day): float(total or 0.0) for day, total in revenue_7d_rows}
    for i in range(6, -1, -1):
        d = today - _s.timedelta(days=i)
        amt = revenue_by_day.get(d.isoformat(), 0.0)
        revenue_7d_bars.append({"date_iso": d.isoformat(), "amount": amt, "label": f"{d.day}/{d.month}"})
        max_rev_7d = max(max_rev_7d, amt)
    for bar in revenue_7d_bars:
        bar["bar_pct"] = int(round(100 * float(bar["amount"]) / max_rev_7d)) if max_rev_7d > 0 else 0
    return revenue_7d_bars


def build_ops_rows_and_schedule_conflicts(
    db: _s.Session,
    cid: int,
    rooms_by_id: dict[int, Any],
    today: Any,
    tomorrow_d: Any,
    now_na: Any,
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]], list[dict[str, str | int]]]:
    ops_sessions_q = (
        db.query(_s.models.YogaSession)
        .filter(
            _s.models.YogaSession.center_id == cid,
            _s.or_(
                _s.func.date(_s.models.YogaSession.starts_at) == today,
                _s.func.date(_s.models.YogaSession.starts_at) == tomorrow_d,
            ),
        )
        .order_by(_s.models.YogaSession.starts_at.asc())
        .limit(36)
        .all()
    )
    ops_spots = _s._spots_available_map(db, cid, [int(s.id) for s in ops_sessions_q])
    ops_today_rows: list[dict[str, str | int]] = []
    ops_tomorrow_rows: list[dict[str, str | int]] = []
    for s in ops_sessions_q:
        room = rooms_by_id.get(s.room_id)
        row = {
            "id": s.id,
            "title": s.title,
            "trainer": s.trainer_name,
            "room": room.name if room else "-",
            "starts": _s._fmt_dt(s.starts_at),
            "spots": ops_spots.get(int(s.id), 0),
            "capacity": room.capacity if room else 0,
        }
        if s.starts_at.date() == today:
            ops_today_rows.append(row)
        elif s.starts_at.date() == tomorrow_d:
            ops_tomorrow_rows.append(row)

    window_start = now_na - _s.timedelta(hours=6)
    future_for_conflicts = (
        db.query(_s.models.YogaSession)
        .filter(_s.models.YogaSession.center_id == cid, _s.models.YogaSession.starts_at >= window_start)
        .order_by(_s.models.YogaSession.room_id, _s.models.YogaSession.starts_at)
        .all()
    )
    by_room_sessions: dict[int, list[_s.models.YogaSession]] = _s.defaultdict(list)
    for s in future_for_conflicts:
        by_room_sessions[s.room_id].append(s)
    schedule_conflicts: list[dict[str, str | int]] = []
    for rid, lst in by_room_sessions.items():
        lst.sort(key=lambda x: x.starts_at)
        for i in range(len(lst) - 1):
            a, b = lst[i], lst[i + 1]
            end_a = a.starts_at + _s.timedelta(minutes=int(a.duration_minutes or 0))
            if end_a > b.starts_at:
                schedule_conflicts.append(
                    {
                        "room_name": (rooms_by_id.get(rid).name if rooms_by_id.get(rid) else f"غرفة #{rid}"),
                        "a_id": a.id,
                        "a_title": a.title,
                        "a_start": _s._fmt_dt(a.starts_at),
                        "b_id": b.id,
                        "b_title": b.title,
                        "b_start": _s._fmt_dt(b.starts_at),
                    }
                )
    return ops_today_rows, ops_tomorrow_rows, schedule_conflicts


def fetch_admin_login_audit_rows(db: _s.Session) -> list[dict[str, str]]:
    return [
        {
            "created_at_display": _s._fmt_dt(ev.created_at),
            "status": ev.status,
            "email": ev.email or "-",
            "ip": ev.ip or "-",
        }
        for ev in db.query(_s.models.SecurityAuditEvent)
        .filter(_s.models.SecurityAuditEvent.event_type == "admin_login")
        .order_by(_s.models.SecurityAuditEvent.created_at.desc())
        .limit(20)
        .all()
    ]


def aggregate_paid_revenue_and_public_user_stats(
    db: _s.Session, cid: int, today: Any
) -> tuple[float, float, int, int, int]:
    recent_public_cutoff = _s.utcnow_naive() - _s.timedelta(days=7)
    paid_revenue_total, paid_revenue_today = (
        db.query(
            _s.func.coalesce(
                _s.func.sum(
                    _s.case(
                        (_s.models.Payment.status == "paid", _s.models.Payment.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
            _s.func.coalesce(
                _s.func.sum(
                    _s.case(
                        (
                            _s.and_(
                                _s.models.Payment.status == "paid",
                                _s.func.date(_s.models.Payment.paid_at) == today,
                            ),
                            _s.models.Payment.amount,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
        )
        .filter(_s.models.Payment.center_id == cid)
        .one()
    )
    scoped_public_users = _s._public_users_query_for_center(db, cid).subquery()
    public_users_count, public_users_deleted_count, public_users_new_7d = (
        db.query(
            _s.func.count(scoped_public_users.c.id),
            _s.func.coalesce(
                _s.func.sum(_s.case((scoped_public_users.c.is_deleted.is_(True), 1), else_=0)),
                0,
            ),
            _s.func.coalesce(
                _s.func.sum(
                    _s.case(
                        (
                            _s.and_(
                                scoped_public_users.c.created_at >= recent_public_cutoff,
                                scoped_public_users.c.is_deleted.is_(False),
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
    return (
        float(paid_revenue_total or 0.0),
        float(paid_revenue_today or 0.0),
        int(public_users_count),
        int(public_users_deleted_count),
        int(public_users_new_7d),
    )


@dataclass(frozen=True)
class SecurityAuditBundle:
    security_event_rows: list[dict[str, Any]]
    security_summary: dict[str, Any]
    block_history_rows: list[dict[str, Any]]
    security_export_url: str
    safe_audit_page: int
    security_events_total: int
    security_events_total_pages: int
    audit_page_size: int


def _risk_level(hits: int) -> str:
    if hits >= 12:
        return "high"
    if hits >= 5:
        return "medium"
    return "low"


def load_security_audit_bundle(
    db: _s.Session,
    *,
    audit_event_type: str,
    audit_status: str,
    audit_email: str,
    audit_ip: str,
    audit_page: int,
) -> SecurityAuditBundle:
    audit_query = db.query(_s.models.SecurityAuditEvent)
    if audit_event_type.strip():
        audit_query = audit_query.filter(_s.models.SecurityAuditEvent.event_type == audit_event_type.strip())
    if audit_status.strip():
        audit_query = audit_query.filter(_s.models.SecurityAuditEvent.status == audit_status.strip())
    if audit_email.strip():
        audit_query = audit_query.filter(
            _s.models.SecurityAuditEvent.email.ilike(f"%{audit_email.strip().lower()}%")
        )
    if audit_ip.strip():
        audit_query = audit_query.filter(_s.models.SecurityAuditEvent.ip.ilike(f"%{audit_ip.strip()}%"))

    audit_page_size = _s.ADMIN_SECURITY_AUDIT_PAGE_SIZE
    security_events_total = audit_query.order_by(None).count()
    safe_audit_page, security_events_total_pages, security_events_offset = normalize_admin_list_page(
        audit_page,
        security_events_total,
        audit_page_size,
    )
    security_events = (
        audit_query.order_by(_s.models.SecurityAuditEvent.created_at.desc())
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
            "created_at_display": _s._fmt_dt(ev.created_at),
        }
        for ev in security_events
    ]
    high_risk_since = _s.utcnow_naive() - _s.timedelta(hours=24)
    failed_logins_24h = (
        db.query(_s.models.SecurityAuditEvent)
        .filter(
            _s.models.SecurityAuditEvent.event_type == "public_login",
            _s.models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
            _s.models.SecurityAuditEvent.created_at >= high_risk_since,
        )
        .count()
    )
    suspicious_ips = (
        db.query(_s.models.SecurityAuditEvent.ip, _s.func.count(_s.models.SecurityAuditEvent.id).label("hits"))
        .filter(
            _s.models.SecurityAuditEvent.event_type == "public_login",
            _s.models.SecurityAuditEvent.status.in_(["invalid_credentials", "rate_limited"]),
            _s.models.SecurityAuditEvent.created_at >= high_risk_since,
        )
        .group_by(_s.models.SecurityAuditEvent.ip)
        .having(_s.func.count(_s.models.SecurityAuditEvent.id) >= 5)
        .order_by(_s.func.count(_s.models.SecurityAuditEvent.id).desc())
        .limit(5)
        .all()
    )
    blocked_ips = (
        db.query(_s.models.BlockedIP)
        .filter(
            _s.models.BlockedIP.is_active.is_(True),
            _s.or_(_s.models.BlockedIP.blocked_until.is_(None), _s.models.BlockedIP.blocked_until > _s.utcnow_naive()),
        )
        .order_by(_s.models.BlockedIP.created_at.desc())
        .limit(20)
        .all()
    )

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
                "blocked_until": _s._fmt_dt(b.blocked_until) if b.blocked_until else "دائم",
            }
            for b in blocked_ips
        ],
    }
    block_history_events = (
        db.query(_s.models.SecurityAuditEvent)
        .filter(_s.models.SecurityAuditEvent.event_type.in_(["admin_ip_block", "admin_ip_unblock"]))
        .order_by(_s.models.SecurityAuditEvent.created_at.desc())
        .limit(120)
        .all()
    )
    block_history_rows = []
    for ev in block_history_events:
        details = {}
        if ev.details_json:
            try:
                details = _s.json.loads(ev.details_json)
            except (TypeError, ValueError):
                details = {}
        block_history_rows.append(
            {
                "id": ev.id,
                "created_at_display": _s._fmt_dt(ev.created_at),
                "event_type": ev.event_type,
                "status": ev.status,
                "admin_email": ev.email or "-",
                "target_ip": details.get("target_ip", "-"),
                "minutes": details.get("minutes", "-"),
                "reason": details.get("reason", "-"),
            }
        )
    security_export_url = _s._url_with_params(
        "/admin/security/export/csv",
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
    )
    return SecurityAuditBundle(
        security_event_rows=security_event_rows,
        security_summary=security_summary,
        block_history_rows=block_history_rows,
        security_export_url=security_export_url,
        safe_audit_page=safe_audit_page,
        security_events_total=security_events_total,
        security_events_total_pages=security_events_total_pages,
        audit_page_size=audit_page_size,
    )


@dataclass(frozen=True)
class RoomsPlansFaqBundle:
    rooms: list[Any]
    plans: list[Any]
    faqs: list[Any]
    rooms_by_id: dict[int, Any]
    room_sort_key: str
    room_ordering: dict[str, Any]


def load_rooms_plans_faqs(db: _s.Session, cid: int, room_sort: str) -> RoomsPlansFaqBundle:
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
    faqs = (
        db.query(_s.models.FAQItem)
        .filter(_s.models.FAQItem.center_id == cid)
        .order_by(_s.models.FAQItem.sort_order.asc(), _s.models.FAQItem.created_at.asc())
        .all()
    )
    rooms_by_id = {r.id: r for r in rooms}
    return RoomsPlansFaqBundle(
        rooms=rooms,
        plans=plans,
        faqs=faqs,
        rooms_by_id=rooms_by_id,
        room_sort_key=room_sort_key,
        room_ordering=room_ordering,
    )


@dataclass(frozen=True)
class SessionPageBundle:
    sessions: list[Any]
    sessions_total: int
    safe_sessions_page: int
    sessions_total_pages: int
    sessions_page_size: int
    session_rows: list[dict[str, Any]]


def load_paginated_session_rows(
    db: _s.Session, cid: int, rooms_by_id: dict[int, Any], sessions_page: int
) -> SessionPageBundle:
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
    now_for_sessions = _s.utcnow_naive()
    session_rows: list[dict[str, Any]] = []
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        session_rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": _SESSION_LEVEL_LABELS.get(s.level, s.level),
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
    return SessionPageBundle(
        sessions=sessions,
        sessions_total=sessions_total,
        safe_sessions_page=safe_sessions_page,
        sessions_total_pages=sessions_total_pages,
        sessions_page_size=sessions_page_size,
        session_rows=session_rows,
    )


def plan_rows_from_plans(plans: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "plan_type": p.plan_type,
            "plan_type_label": _PLAN_TYPE_LABELS.get(p.plan_type, p.plan_type),
            "price": p.price,
            "session_limit": p.session_limit,
            "is_active": p.is_active,
        }
        for p in plans
    ]


def faq_rows_from_faqs(faqs: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "question": f.question,
            "answer": f.answer,
            "sort_order": f.sort_order,
            "is_active": f.is_active,
        }
        for f in faqs
    ]


@dataclass(frozen=True)
class PublicUsersPageBundle:
    public_users: list[Any]
    public_users_total: int
    safe_public_user_page: int
    public_users_total_pages: int
    public_users_page_size: int
    status_key: str
    verified_key: str


def load_filtered_public_users_page(
    db: _s.Session,
    cid: int,
    public_user_q: str,
    public_user_status: str,
    public_user_verified: str,
    public_user_page: int,
) -> PublicUsersPageBundle:
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
    return PublicUsersPageBundle(
        public_users=public_users,
        public_users_total=public_users_total,
        safe_public_user_page=safe_public_user_page,
        public_users_total_pages=public_users_total_pages,
        public_users_page_size=public_users_page_size,
        status_key=status_key,
        verified_key=verified_key,
    )


@dataclass(frozen=True)
class TrashUsersPageBundle:
    trash_users_list: list[Any]
    trash_total: int
    safe_trash_page: int
    trash_total_pages: int


def load_trash_users_page(
    db: _s.Session, cid: int, trash_q: str, trash_page: int, page_size: int
) -> TrashUsersPageBundle:
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
        page_size,
    )
    trash_users_list = (
        trash_base.order_by(_s.models.PublicUser.deleted_at.desc(), _s.models.PublicUser.id.desc())
        .offset(trash_offset)
        .limit(page_size)
        .all()
    )
    return TrashUsersPageBundle(
        trash_users_list=trash_users_list,
        trash_total=trash_total,
        safe_trash_page=safe_trash_page,
        trash_total_pages=trash_total_pages,
    )


def build_dashboard_summary_dict(
    db: _s.Session,
    cid: int,
    rooms: Sequence[Any],
    sessions_total: int,
    plans: Sequence[Any],
    paid_revenue_total: float,
    paid_revenue_today: float,
    public_users_count: int,
    public_users_deleted_count: int,
    public_users_new_7d: int,
) -> dict[str, Any]:
    return {
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


@dataclass(frozen=True)
class PaymentsPageBundle:
    payment_rows: list[dict[str, Any]]
    payments_total: int
    safe_payments_page: int
    payments_total_pages: int
    payments_page_size: int


def load_paginated_payment_rows(
    db: _s.Session,
    cid: int,
    payment_from_dt: Any,
    payment_to_dt: Any,
    payments_page: int,
) -> PaymentsPageBundle:
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
    return PaymentsPageBundle(
        payment_rows=payment_rows,
        payments_total=payments_total,
        safe_payments_page=safe_payments_page,
        payments_total_pages=payments_total_pages,
        payments_page_size=payments_page_size,
    )


def build_loyalty_public_and_trash_rows(
    public_users: Sequence[Any],
    trash_users_list: Sequence[Any],
    loyalty_by_email: dict[str, int],
    center: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public_user_rows: list[dict[str, Any]] = []
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
    trash_user_rows: list[dict[str, Any]] = []
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
    return public_user_rows, trash_user_rows


@dataclass(frozen=True)
class CenterPostsBundle:
    center_post_admin_rows: list[dict[str, Any]]
    editing_post: dict[str, Any] | None
    center_post_type_choices: list[dict[str, str]]
    safe_post_edit: int
    safe_center_posts_page: int
    center_posts_total: int
    center_posts_total_pages: int
    center_posts_page_size: int


def load_center_posts_admin_section(
    db: _s.Session,
    cid: int,
    center_posts_page: int,
    post_edit: int,
    post_edit_url: Callable[[int], str],
) -> CenterPostsBundle:
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
        center_posts_base_query.offset(center_posts_offset).limit(center_posts_page_size).all()
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

    center_post_admin_rows: list[dict[str, Any]] = []
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
                "edit_url": post_edit_url(cp.id),
            }
        )

    editing_post: dict[str, Any] | None = None
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

    return CenterPostsBundle(
        center_post_admin_rows=center_post_admin_rows,
        editing_post=editing_post,
        center_post_type_choices=center_post_type_choices,
        safe_post_edit=safe_post_edit,
        safe_center_posts_page=safe_center_posts_page,
        center_posts_total=center_posts_total,
        center_posts_total_pages=center_posts_total_pages,
        center_posts_page_size=center_posts_page_size,
    )


def build_admin_insight_cards(
    dash_home: str, kpi: AdminKpiCounts, schedule_conflicts: Sequence[Any]
) -> list[dict[str, str]]:
    admin_insights: list[dict[str, str]] = []
    if kpi.sessions_today_no_bookings:
        admin_insights.append(
            {
                "label": f"جلسات اليوم بلا حجوزات نشطة: {kpi.sessions_today_no_bookings}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )
    if kpi.subs_expiring_7d:
        admin_insights.append(
            {
                "label": f"اشتراكات تنتهي خلال 7 أيام: {kpi.subs_expiring_7d}",
                "href": f"{dash_home}#section-plans",
                "kind": "info",
            }
        )
    if kpi.public_users_unverified_count:
        admin_insights.append(
            {
                "label": f"مستخدمون غير موثّقين (عام): {kpi.public_users_unverified_count}",
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
    if kpi.pending_payments_stale_8d:
        admin_insights.append(
            {
                "label": f"معلّقات قديمة (+8 أيام): {kpi.pending_payments_stale_8d}",
                "href": "/admin/reports/health",
                "kind": "warn",
            }
        )
    if kpi.failed_payments_7d:
        admin_insights.append(
            {
                "label": f"مدفوعات فاشلة في آخر 7 أيام: {kpi.failed_payments_7d}",
                "href": "/admin/reports/health",
                "kind": "warn",
            }
        )
    return admin_insights


def build_morning_brief_dict(kpi: AdminKpiCounts, paid_revenue_today: float) -> dict[str, Any]:
    return {
        "sessions_today": kpi.sessions_scheduled_today,
        "bookings_today": kpi.bookings_active_today,
        "revenue_today": float(paid_revenue_today or 0),
        "pending_stale_8d": kpi.pending_payments_stale_8d,
        "failed_7d": kpi.failed_payments_7d,
        "subs_expiring_7d": kpi.subs_expiring_7d,
    }


def build_data_export_urls(payment_date_from: str, payment_date_to: str) -> tuple[dict[str, str], str, str]:
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
    return data_export_urls, pf, pt


def build_loyalty_admin_dict(center: Any) -> dict[str, Any]:
    _env_b, _env_s, _env_g = _s.loyalty_thresholds()
    _eff_b, _eff_s, _eff_g = _s.effective_loyalty_thresholds(center)
    return {
        "env": {"bronze": _env_b, "silver": _env_s, "gold": _env_g},
        "effective": {"bronze": _eff_b, "silver": _eff_s, "gold": _eff_g},
    }

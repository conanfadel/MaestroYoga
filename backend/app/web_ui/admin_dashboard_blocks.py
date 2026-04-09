"""Query and small-build helpers for the admin dashboard (used by admin_dashboard_context)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import impl_state as _s


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

"""DB queries and aggregations for the admin dashboard context (GET /admin)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks import (
    aggregate_paid_revenue_and_public_user_stats,
    build_dashboard_summary_dict,
    build_loyalty_public_and_trash_rows,
    build_ops_rows_and_schedule_conflicts,
    build_revenue_7d_bars,
    faq_rows_from_faqs,
    fetch_admin_kpi_counts,
    fetch_admin_login_audit_rows,
    load_filtered_public_users_page,
    load_paginated_payment_rows,
    load_paginated_session_rows,
    load_rooms_plans_faqs,
    load_security_audit_bundle,
    load_trash_users_page,
    plan_rows_from_plans,
)


@dataclass(frozen=True)
class AdminDashboardQueryState:
    cid: int
    center: _s.models.Center | None
    rooms: list[Any]
    room_sort_key: str
    room_ordering: dict[str, Any]
    sessions_total: int
    safe_sessions_page: int
    sessions_total_pages: int
    sessions_page_size: int
    session_rows: list[Any]
    public_users_total: int
    safe_public_user_page: int
    public_users_total_pages: int
    public_users_page_size: int
    status_key: str
    verified_key: str
    trash_total: int
    safe_trash_page: int
    trash_total_pages: int
    plan_rows: list[Any]
    faq_rows: list[Any]
    kpi: Any
    revenue_7d_bars: Any
    ops_today_rows: Any
    ops_tomorrow_rows: Any
    schedule_conflicts: Any
    admin_login_audit_rows: Any
    dashboard: dict[str, Any]
    payment_rows: list[Any]
    payments_total: int
    safe_payments_page: int
    payments_total_pages: int
    payments_page_size: int
    public_user_rows: list[Any]
    trash_user_rows: list[Any]
    security_event_rows: list[Any]
    security_summary: Any
    block_history_rows: list[Any]
    security_export_url: str | None
    safe_audit_page: int
    security_events_total: int
    security_events_total_pages: int
    audit_page_size: int
    paid_revenue_today: Any
    room_sort: str
    public_user_q: str
    public_user_status: str
    public_user_verified: str
    trash_q: str
    audit_event_type: str
    audit_status: str
    audit_email: str
    audit_ip: str
    payment_date_from: str
    payment_date_to: str
    center_posts_page: int
    post_edit: int


def load_admin_dashboard_query_state(
    *,
    db: _s.Session,
    user: _s.models.User,
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
) -> AdminDashboardQueryState:
    cid = _s.require_user_center_id(user)
    center = db.get(_s.models.Center, cid)
    if center:
        if center.name == _s.DEMO_CENTER_NAME:
            _s.ensure_demo_news_posts(db, center.id)
        _s._clear_center_branding_urls_if_files_missing(db, center)
    rpf = load_rooms_plans_faqs(db, cid, room_sort)
    rooms = rpf.rooms
    plans = rpf.plans
    faqs = rpf.faqs
    rooms_by_id = rpf.rooms_by_id
    room_sort_key = rpf.room_sort_key
    room_ordering = rpf.room_ordering

    sp = load_paginated_session_rows(db, cid, rooms_by_id, sessions_page)
    sessions_total = sp.sessions_total
    safe_sessions_page = sp.safe_sessions_page
    sessions_total_pages = sp.sessions_total_pages
    sessions_page_size = sp.sessions_page_size
    session_rows = sp.session_rows

    pub = load_filtered_public_users_page(
        db,
        cid,
        public_user_q,
        public_user_status,
        public_user_verified,
        public_user_page,
    )
    public_users = pub.public_users
    public_users_total = pub.public_users_total
    safe_public_user_page = pub.safe_public_user_page
    public_users_total_pages = pub.public_users_total_pages
    public_users_page_size = pub.public_users_page_size
    status_key = pub.status_key
    verified_key = pub.verified_key

    trash_b = load_trash_users_page(db, cid, trash_q, trash_page, public_users_page_size)
    trash_users_list = trash_b.trash_users_list
    trash_total = trash_b.trash_total
    safe_trash_page = trash_b.safe_trash_page
    trash_total_pages = trash_b.trash_total_pages

    plan_rows = plan_rows_from_plans(plans)
    faq_rows = faq_rows_from_faqs(faqs)

    today = _s.utcnow_naive().date()
    tomorrow_d = today + _s.timedelta(days=1)
    now_na = _s.utcnow_naive()
    payment_from_dt = _s._parse_optional_date_str(payment_date_from)
    payment_to_dt = _s._parse_optional_date_str(payment_date_to)

    kpi = fetch_admin_kpi_counts(db, cid, today, now_na)

    revenue_7d_bars = build_revenue_7d_bars(db, cid, today)

    ops_today_rows, ops_tomorrow_rows, schedule_conflicts = build_ops_rows_and_schedule_conflicts(
        db, cid, rooms_by_id, today, tomorrow_d, now_na
    )

    admin_login_audit_rows = fetch_admin_login_audit_rows(db)

    paid_revenue_total, paid_revenue_today, public_users_count, public_users_deleted_count, public_users_new_7d = (
        aggregate_paid_revenue_and_public_user_stats(db, cid, today)
    )
    dashboard = build_dashboard_summary_dict(
        db,
        cid,
        rooms,
        sessions_total,
        plans,
        paid_revenue_total,
        paid_revenue_today,
        public_users_count,
        public_users_deleted_count,
        public_users_new_7d,
    )

    pay_b = load_paginated_payment_rows(db, cid, payment_from_dt, payment_to_dt, payments_page)
    payment_rows = pay_b.payment_rows
    payments_total = pay_b.payments_total
    safe_payments_page = pay_b.safe_payments_page
    payments_total_pages = pay_b.payments_total_pages
    payments_page_size = pay_b.payments_page_size

    loyalty_by_email = _s.loyalty_confirmed_counts_by_email_lower(db, cid)
    public_user_rows, trash_user_rows = build_loyalty_public_and_trash_rows(
        public_users, trash_users_list, loyalty_by_email, center
    )

    sec = load_security_audit_bundle(
        db,
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
        audit_page=audit_page,
    )

    return AdminDashboardQueryState(
        cid=cid,
        center=center,
        rooms=rooms,
        room_sort_key=room_sort_key,
        room_ordering=room_ordering,
        sessions_total=sessions_total,
        safe_sessions_page=safe_sessions_page,
        sessions_total_pages=sessions_total_pages,
        sessions_page_size=sessions_page_size,
        session_rows=session_rows,
        public_users_total=public_users_total,
        safe_public_user_page=safe_public_user_page,
        public_users_total_pages=public_users_total_pages,
        public_users_page_size=public_users_page_size,
        status_key=status_key,
        verified_key=verified_key,
        trash_total=trash_total,
        safe_trash_page=safe_trash_page,
        trash_total_pages=trash_total_pages,
        plan_rows=plan_rows,
        faq_rows=faq_rows,
        kpi=kpi,
        revenue_7d_bars=revenue_7d_bars,
        ops_today_rows=ops_today_rows,
        ops_tomorrow_rows=ops_tomorrow_rows,
        schedule_conflicts=schedule_conflicts,
        admin_login_audit_rows=admin_login_audit_rows,
        dashboard=dashboard,
        payment_rows=payment_rows,
        payments_total=payments_total,
        safe_payments_page=safe_payments_page,
        payments_total_pages=payments_total_pages,
        payments_page_size=payments_page_size,
        public_user_rows=public_user_rows,
        trash_user_rows=trash_user_rows,
        security_event_rows=sec.security_event_rows,
        security_summary=sec.security_summary,
        block_history_rows=sec.block_history_rows,
        security_export_url=sec.security_export_url,
        safe_audit_page=sec.safe_audit_page,
        security_events_total=sec.security_events_total,
        security_events_total_pages=sec.security_events_total_pages,
        audit_page_size=sec.audit_page_size,
        paid_revenue_today=paid_revenue_today,
        room_sort=room_sort,
        public_user_q=public_user_q,
        public_user_status=public_user_status,
        public_user_verified=public_user_verified,
        trash_q=trash_q,
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
        payment_date_from=payment_date_from,
        payment_date_to=payment_date_to,
        center_posts_page=center_posts_page,
        post_edit=post_edit,
    )

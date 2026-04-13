"""DB queries and aggregations for the admin dashboard context (GET /admin)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import impl_state as _s
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
    training_exercises: list[Any]
    selected_muscle: str
    training_client_q: str
    training_client_id: int
    training_tab: str
    training_client_options: list[dict[str, Any]]
    training_client_sessions: list[dict[str, Any]]
    training_client_assignments: list[Any]
    training_medical_profile: Any
    training_medical_history: list[Any]


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
    training_muscle: str,
    training_client_q: str,
    training_client_id: int,
    training_tab: str,
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
    client_rows_for_numbers = (
        db.query(_s.models.Client.email, _s.models.Client.subscription_number)
        .filter(_s.models.Client.center_id == cid)
        .all()
    )
    subscription_number_by_email: dict[str, int | None] = {}
    for email_value, sub_number in client_rows_for_numbers:
        email_key = (email_value or "").strip().lower()
        if not email_key:
            continue
        if email_key not in subscription_number_by_email:
            subscription_number_by_email[email_key] = int(sub_number) if sub_number else None
    public_user_rows, trash_user_rows = build_loyalty_public_and_trash_rows(
        public_users,
        trash_users_list,
        loyalty_by_email,
        center,
        subscription_number_by_email=subscription_number_by_email,
    )

    sec = load_security_audit_bundle(
        db,
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
        audit_page=audit_page,
    )

    selected_muscle = (training_muscle or "").strip().lower()
    if selected_muscle not in _s.TRAINING_MUSCLE_KEY_SET:
        selected_muscle = "core"
    training_exercises = (
        db.query(_s.models.TrainingExercise)
        .filter(
            _s.models.TrainingExercise.center_id == cid,
            _s.models.TrainingExercise.muscle_key == selected_muscle,
        )
        .order_by(_s.models.TrainingExercise.created_at.desc(), _s.models.TrainingExercise.id.desc())
        .all()
    )
    training_client_q_clean = (training_client_q or "").strip()
    training_client_options_query = (
        db.query(_s.models.Client)
        .filter(_s.models.Client.center_id == cid)
        .order_by(_s.models.Client.created_at.desc(), _s.models.Client.id.desc())
    )
    if training_client_q_clean:
        like_q = f"%{training_client_q_clean.lower()}%"
        numeric_q = None
        try:
            numeric_q = int(training_client_q_clean)
        except ValueError:
            numeric_q = None
        conditions = [
            _s.func.lower(_s.models.Client.full_name).like(like_q),
            _s.func.lower(_s.models.Client.email).like(like_q),
            _s.func.coalesce(_s.models.Client.phone, "").like(f"%{training_client_q_clean}%"),
        ]
        if numeric_q is not None and numeric_q > 0:
            conditions.append(_s.models.Client.subscription_number == numeric_q)
        training_client_options_query = training_client_options_query.filter(
            _s.or_(*conditions)
        )
    training_client_rows = training_client_options_query.limit(100).all()
    training_client_options: list[dict[str, Any]] = []
    for c in training_client_rows:
        training_client_options.append(
            {
                "id": c.id,
                "full_name": c.full_name or "-",
                "email": c.email or "-",
                "phone": c.phone or "-",
                "subscription_number_display": _s.format_client_subscription_number(c.subscription_number),
            }
        )
    selected_training_client_id = int(training_client_id or 0)
    if selected_training_client_id <= 0 and training_client_options:
        selected_training_client_id = int(training_client_options[0]["id"])

    training_client_assignments: list[Any] = []
    training_client_sessions: list[dict[str, Any]] = []
    training_medical_profile = None
    training_medical_history: list[Any] = []
    if selected_training_client_id > 0:
        booking_rows = (
            db.query(_s.models.Booking, _s.models.YogaSession)
            .join(_s.models.YogaSession, _s.models.YogaSession.id == _s.models.Booking.session_id)
            .filter(
                _s.models.Booking.center_id == cid,
                _s.models.Booking.client_id == selected_training_client_id,
                _s.models.Booking.status.in_(("booked", "confirmed", "pending_payment")),
                _s.models.YogaSession.center_id == cid,
            )
            .order_by(_s.models.YogaSession.starts_at.desc(), _s.models.YogaSession.id.desc())
            .all()
        )
        seen_session_ids: set[int] = set()
        for _booking, ys in booking_rows:
            if not ys or ys.id in seen_session_ids:
                continue
            seen_session_ids.add(ys.id)
            training_client_sessions.append(
                {
                    "id": ys.id,
                    "title": ys.title or "-",
                    "trainer_name": ys.trainer_name or "-",
                    "starts_at_display": _s._fmt_dt(ys.starts_at),
                }
            )
        training_client_assignments = (
            db.query(_s.models.TrainingAssignmentBatch)
            .filter(
                _s.models.TrainingAssignmentBatch.center_id == cid,
                _s.models.TrainingAssignmentBatch.client_id == selected_training_client_id,
            )
            .order_by(
                _s.models.TrainingAssignmentBatch.created_at.desc(),
                _s.models.TrainingAssignmentBatch.id.desc(),
            )
            .all()
        )
    selected_training_tab = (training_tab or "").strip().lower()
    if selected_training_tab not in {"assignments", "medical"}:
        selected_training_tab = "assignments"
    if selected_training_client_id > 0:
        training_medical_profile = (
            db.query(_s.models.ClientMedicalProfile)
            .filter(
                _s.models.ClientMedicalProfile.center_id == cid,
                _s.models.ClientMedicalProfile.client_id == selected_training_client_id,
            )
            .first()
        )
        training_medical_history = (
            db.query(_s.models.ClientMedicalHistoryEntry)
            .filter(
                _s.models.ClientMedicalHistoryEntry.center_id == cid,
                _s.models.ClientMedicalHistoryEntry.client_id == selected_training_client_id,
            )
            .order_by(
                _s.models.ClientMedicalHistoryEntry.event_date.desc(),
                _s.models.ClientMedicalHistoryEntry.created_at.desc(),
                _s.models.ClientMedicalHistoryEntry.id.desc(),
            )
            .limit(200)
            .all()
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
        training_exercises=training_exercises,
        selected_muscle=selected_muscle,
        training_client_q=training_client_q_clean,
        training_client_id=selected_training_client_id,
        training_tab=selected_training_tab,
        training_client_options=training_client_options,
        training_client_sessions=training_client_sessions,
        training_client_assignments=training_client_assignments,
        training_medical_profile=training_medical_profile,
        training_medical_history=training_medical_history,
    )

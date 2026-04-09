"""Build template context for the admin dashboard (GET /admin)."""

from __future__ import annotations

from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks import (
    aggregate_paid_revenue_and_public_user_stats,
    build_admin_insight_cards,
    build_data_export_urls,
    build_loyalty_admin_dict,
    build_loyalty_public_and_trash_rows,
    build_morning_brief_dict,
    build_ops_rows_and_schedule_conflicts,
    build_dashboard_summary_dict,
    build_revenue_7d_bars,
    faq_rows_from_faqs,
    fetch_admin_kpi_counts,
    fetch_admin_login_audit_rows,
    load_center_posts_admin_section,
    load_filtered_public_users_page,
    load_paginated_payment_rows,
    load_paginated_session_rows,
    load_rooms_plans_faqs,
    load_security_audit_bundle,
    load_trash_users_page,
    normalize_admin_list_page,
    plan_rows_from_plans,
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

    def _post_admin_edit_url(edit_id: int) -> str:
        return _admin_page_url(**{_s.ADMIN_QP_POST_EDIT: str(edit_id)}) + "#section-center-posts"

    cp_b = load_center_posts_admin_section(
        db, cid, center_posts_page, post_edit, _post_admin_edit_url
    )
    center_post_admin_rows = cp_b.center_post_admin_rows
    editing_post = cp_b.editing_post
    center_post_type_choices = cp_b.center_post_type_choices
    safe_post_edit = cp_b.safe_post_edit
    safe_center_posts_page = cp_b.safe_center_posts_page
    center_posts_total = cp_b.center_posts_total
    center_posts_total_pages = cp_b.center_posts_total_pages
    center_posts_page_size = cp_b.center_posts_page_size

    center_posts_page_prev_url = _admin_page_url(
        **{"center_posts_page": str(max(1, safe_center_posts_page - 1))}
    )
    center_posts_page_next_url = _admin_page_url(
        **{"center_posts_page": str(min(center_posts_total_pages, safe_center_posts_page + 1))}
    )

    dash_home = _admin_page_url()
    admin_insights = build_admin_insight_cards(dash_home, kpi, schedule_conflicts)
    morning_brief = build_morning_brief_dict(kpi, paid_revenue_today)
    data_export_urls, pf, pt = build_data_export_urls(payment_date_from, payment_date_to)
    loyalty_admin = build_loyalty_admin_dict(center)

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

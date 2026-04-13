"""URLs, center posts section, and final template dict for GET /admin."""

from __future__ import annotations

from typing import Any

from .. import impl_state as _s
from .admin_dashboard_blocks import (
    build_admin_insight_cards,
    build_data_export_urls,
    build_loyalty_admin_dict,
    build_morning_brief_dict,
    load_center_posts_admin_section,
)
from .admin_dashboard_context_load import AdminDashboardQueryState


def finalize_admin_dashboard_template_context(
    *,
    db: _s.Session,
    user: _s.models.User,
    msg: str | None,
    state: AdminDashboardQueryState,
) -> dict[str, Any]:
    admin_flash = None
    if msg:
        flash_data = _s.ADMIN_FLASH_MESSAGES.get(msg)
        if flash_data:
            text, level = flash_data
            admin_flash = {"text": text, "level": level}

    base_admin_params = {
        _s.ADMIN_QP_ROOM_SORT: state.room_sort,
        _s.ADMIN_QP_PUBLIC_USER_Q: state.public_user_q,
        _s.ADMIN_QP_PUBLIC_USER_STATUS: state.public_user_status,
        _s.ADMIN_QP_PUBLIC_USER_VERIFIED: state.public_user_verified,
        _s.ADMIN_QP_PUBLIC_USER_PAGE: str(state.safe_public_user_page),
        _s.ADMIN_QP_TRASH_PAGE: str(state.safe_trash_page),
        _s.ADMIN_QP_TRASH_Q: state.trash_q,
        _s.ADMIN_QP_SESSIONS_PAGE: str(state.safe_sessions_page),
        _s.ADMIN_QP_PAYMENTS_PAGE: str(state.safe_payments_page),
        _s.ADMIN_QP_AUDIT_EVENT_TYPE: state.audit_event_type,
        _s.ADMIN_QP_AUDIT_STATUS: state.audit_status,
        _s.ADMIN_QP_AUDIT_EMAIL: state.audit_email,
        _s.ADMIN_QP_AUDIT_IP: state.audit_ip,
        _s.ADMIN_QP_AUDIT_PAGE: str(state.safe_audit_page),
        _s.ADMIN_QP_PAYMENT_DATE_FROM: (state.payment_date_from or "").strip()[:32],
        _s.ADMIN_QP_PAYMENT_DATE_TO: (state.payment_date_to or "").strip()[:32],
        "center_posts_page": str(max(1, int(state.center_posts_page or 1))),
        "training_muscle": state.selected_muscle,
        "training_client_q": state.training_client_q,
        "training_client_id": str(max(0, int(state.training_client_id or 0))),
        "training_tab": state.training_tab,
    }

    def _admin_page_url(**overrides: str) -> str:
        params = dict(base_admin_params)
        for k, v in overrides.items():
            params[k] = v
        return _s._url_with_params("/admin", **params)

    public_users_page_prev_url = _admin_page_url(
        **{_s.ADMIN_QP_PUBLIC_USER_PAGE: str(max(1, state.safe_public_user_page - 1))}
    )
    public_users_page_next_url = _admin_page_url(
        **{
            _s.ADMIN_QP_PUBLIC_USER_PAGE: str(
                min(state.public_users_total_pages, state.safe_public_user_page + 1)
            )
        }
    )
    security_page_prev_url = _admin_page_url(
        **{_s.ADMIN_QP_AUDIT_PAGE: str(max(1, state.safe_audit_page - 1))}
    )
    security_page_next_url = _admin_page_url(
        **{
            _s.ADMIN_QP_AUDIT_PAGE: str(
                min(state.security_events_total_pages, state.safe_audit_page + 1)
            )
        }
    )
    sessions_page_prev_url = _admin_page_url(
        **{_s.ADMIN_QP_SESSIONS_PAGE: str(max(1, state.safe_sessions_page - 1))}
    )
    sessions_page_next_url = _admin_page_url(
        **{
            _s.ADMIN_QP_SESSIONS_PAGE: str(
                min(state.sessions_total_pages, state.safe_sessions_page + 1)
            )
        }
    )
    payments_page_prev_url = _admin_page_url(
        **{_s.ADMIN_QP_PAYMENTS_PAGE: str(max(1, state.safe_payments_page - 1))}
    )
    payments_page_next_url = _admin_page_url(
        **{
            _s.ADMIN_QP_PAYMENTS_PAGE: str(
                min(state.payments_total_pages, state.safe_payments_page + 1)
            )
        }
    )
    trash_page_prev_url = _admin_page_url(
        **{_s.ADMIN_QP_TRASH_PAGE: str(max(1, state.safe_trash_page - 1))}
    )
    trash_page_next_url = _admin_page_url(
        **{_s.ADMIN_QP_TRASH_PAGE: str(min(state.trash_total_pages, state.safe_trash_page + 1))}
    )

    def _post_admin_edit_url(edit_id: int) -> str:
        return _admin_page_url(**{_s.ADMIN_QP_POST_EDIT: str(edit_id)}) + "#section-center-posts"

    cp_b = load_center_posts_admin_section(
        db, state.cid, state.center_posts_page, state.post_edit, _post_admin_edit_url
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
    admin_insights = build_admin_insight_cards(dash_home, state.kpi, state.schedule_conflicts)
    morning_brief = build_morning_brief_dict(state.kpi, state.paid_revenue_today)
    data_export_urls, pf, pt = build_data_export_urls(state.payment_date_from, state.payment_date_to)
    loyalty_admin = build_loyalty_admin_dict(state.center)

    index_page_cfg = (
        _s.merge_index_page_config(state.center) if state.center else _s._default_index_page_config()
    )

    return {
        "user": user,
        "center": state.center,
        "index_page": index_page_cfg,
        "msg": msg,
        "admin_flash": admin_flash,
        "dashboard": state.dashboard,
        "rooms": state.rooms,
        "plans": state.plan_rows,
        "sessions": state.session_rows,
        "recent_payments": state.payment_rows,
        "public_users": state.public_user_rows,
        "faq_items": state.faq_rows,
        "security_events": state.security_event_rows,
        "security_summary": state.security_summary,
        "security_export_url": state.security_export_url,
        "block_history": state.block_history_rows,
        "security_filters": {
            "event_type": state.audit_event_type,
            "status": state.audit_status,
            "email": state.audit_email,
            "ip": state.audit_ip,
        },
        "public_user_filters": {
            "q": state.public_user_q,
            "status": state.status_key,
            "verified": state.verified_key or "all",
        },
        "public_user_pagination": {
            "page": state.safe_public_user_page,
            "page_size": state.public_users_page_size,
            "total": state.public_users_total,
            "total_pages": state.public_users_total_pages,
            "has_prev": state.safe_public_user_page > 1,
            "has_next": state.safe_public_user_page < state.public_users_total_pages,
            "prev_url": public_users_page_prev_url,
            "next_url": public_users_page_next_url,
        },
        "trash_users": state.trash_user_rows,
        "trash_filters": {"q": state.trash_q},
        "trash_pagination": {
            "page": state.safe_trash_page,
            "page_size": state.public_users_page_size,
            "total": state.trash_total,
            "total_pages": state.trash_total_pages,
            "has_prev": state.safe_trash_page > 1,
            "has_next": state.safe_trash_page < state.trash_total_pages,
            "prev_url": trash_page_prev_url,
            "next_url": trash_page_next_url,
        },
        "security_pagination": {
            "page": state.safe_audit_page,
            "page_size": state.audit_page_size,
            "total": state.security_events_total,
            "total_pages": state.security_events_total_pages,
            "has_prev": state.safe_audit_page > 1,
            "has_next": state.safe_audit_page < state.security_events_total_pages,
            "prev_url": security_page_prev_url,
            "next_url": security_page_next_url,
        },
        "sessions_pagination": {
            "page": state.safe_sessions_page,
            "page_size": state.sessions_page_size,
            "total": state.sessions_total,
            "total_pages": state.sessions_total_pages,
            "has_prev": state.safe_sessions_page > 1,
            "has_next": state.safe_sessions_page < state.sessions_total_pages,
            "prev_url": sessions_page_prev_url,
            "next_url": sessions_page_next_url,
        },
        "payments_pagination": {
            "page": state.safe_payments_page,
            "page_size": state.payments_page_size,
            "total": state.payments_total,
            "total_pages": state.payments_total_pages,
            "has_prev": state.safe_payments_page > 1,
            "has_next": state.safe_payments_page < state.payments_total_pages,
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
                state.room_sort_key
                if state.room_sort_key in state.room_ordering
                or state.room_sort_key in {"sessions_desc", "sessions_asc"}
                else "id_asc"
            ),
        },
        "center_id": state.cid,
        "admin_public_index_url": _s._url_with_params("/index", center_id=str(state.cid)),
        "admin_insights": admin_insights,
        "morning_brief": morning_brief,
        "revenue_7d_bars": state.revenue_7d_bars,
        "ops_today_rows": state.ops_today_rows,
        "ops_tomorrow_rows": state.ops_tomorrow_rows,
        "schedule_conflicts": state.schedule_conflicts,
        "admin_login_audit_rows": state.admin_login_audit_rows,
        "data_export_urls": data_export_urls,
        "payment_date_from_value": pf,
        "payment_date_to_value": pt,
        "loyalty_admin": loyalty_admin,
        "training_muscle_options": _s.TRAINING_MUSCLE_OPTIONS,
        "training_selected_muscle": state.selected_muscle,
        "training_selected_muscle_label": _s.TRAINING_MUSCLE_LABELS.get(
            state.selected_muscle, state.selected_muscle
        ),
        "training_exercises": state.training_exercises,
        "training_client_q": state.training_client_q,
        "training_client_id": state.training_client_id,
        "training_tab": state.training_tab,
        "training_client_options": state.training_client_options,
        "training_client_sessions": state.training_client_sessions,
        "training_client_assignments": state.training_client_assignments,
        "training_medical_profile": state.training_medical_profile,
        "training_medical_history": state.training_medical_history,
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

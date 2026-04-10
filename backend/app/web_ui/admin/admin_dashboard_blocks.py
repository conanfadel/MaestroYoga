"""Query and small-build helpers for the admin dashboard (used by admin_dashboard_context)."""

from __future__ import annotations

from .admin_dashboard_blocks_entities import (
    CenterPostsBundle,
    PaymentsPageBundle,
    PublicUsersPageBundle,
    RoomsPlansFaqBundle,
    SessionPageBundle,
    TrashUsersPageBundle,
    build_dashboard_summary_dict,
    build_loyalty_public_and_trash_rows,
    faq_rows_from_faqs,
    load_center_posts_admin_section,
    load_filtered_public_users_page,
    load_paginated_payment_rows,
    load_paginated_session_rows,
    load_rooms_plans_faqs,
    load_trash_users_page,
    plan_rows_from_plans,
)
from .admin_dashboard_blocks_kpi import (
    AdminKpiCounts,
    aggregate_paid_revenue_and_public_user_stats,
    build_ops_rows_and_schedule_conflicts,
    build_revenue_7d_bars,
    fetch_admin_kpi_counts,
    fetch_admin_login_audit_rows,
)
from .admin_dashboard_blocks_pagination import normalize_admin_list_page
from .admin_dashboard_blocks_security import SecurityAuditBundle, load_security_audit_bundle
from .admin_dashboard_blocks_ui import (
    build_admin_insight_cards,
    build_data_export_urls,
    build_loyalty_admin_dict,
    build_morning_brief_dict,
)

__all__ = [
    "AdminKpiCounts",
    "CenterPostsBundle",
    "PaymentsPageBundle",
    "PublicUsersPageBundle",
    "RoomsPlansFaqBundle",
    "SecurityAuditBundle",
    "SessionPageBundle",
    "TrashUsersPageBundle",
    "aggregate_paid_revenue_and_public_user_stats",
    "build_admin_insight_cards",
    "build_dashboard_summary_dict",
    "build_data_export_urls",
    "build_loyalty_admin_dict",
    "build_loyalty_public_and_trash_rows",
    "build_morning_brief_dict",
    "build_ops_rows_and_schedule_conflicts",
    "build_revenue_7d_bars",
    "faq_rows_from_faqs",
    "fetch_admin_kpi_counts",
    "fetch_admin_login_audit_rows",
    "load_center_posts_admin_section",
    "load_filtered_public_users_page",
    "load_paginated_payment_rows",
    "load_paginated_session_rows",
    "load_rooms_plans_faqs",
    "load_security_audit_bundle",
    "load_trash_users_page",
    "normalize_admin_list_page",
    "plan_rows_from_plans",
]

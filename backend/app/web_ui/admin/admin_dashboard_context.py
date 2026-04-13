"""Build template context for the admin dashboard (GET /admin)."""

from __future__ import annotations

from typing import Any

from .. import impl_state as _s
from .admin_dashboard_context_compose import finalize_admin_dashboard_template_context
from .admin_dashboard_context_load import load_admin_dashboard_query_state


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
    training_muscle: str,
) -> dict[str, Any]:
    """Load rooms, users, payments, security, posts, and aggregate KPIs for admin.html."""
    state = load_admin_dashboard_query_state(
        db=db,
        user=user,
        room_sort=room_sort,
        public_user_q=public_user_q,
        public_user_status=public_user_status,
        public_user_verified=public_user_verified,
        public_user_page=public_user_page,
        trash_page=trash_page,
        trash_q=trash_q,
        sessions_page=sessions_page,
        payments_page=payments_page,
        audit_event_type=audit_event_type,
        audit_status=audit_status,
        audit_email=audit_email,
        audit_ip=audit_ip,
        audit_page=audit_page,
        payment_date_from=payment_date_from,
        payment_date_to=payment_date_to,
        post_edit=post_edit,
        center_posts_page=center_posts_page,
        training_muscle=training_muscle,
    )
    return finalize_admin_dashboard_template_context(db=db, user=user, msg=msg, state=state)

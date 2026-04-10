"""Admin dashboard main HTML page (GET /admin)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s
from .admin_dashboard_context import build_admin_dashboard_template_context


def register_admin_dashboard_routes(router: APIRouter) -> None:
    """Large dashboard view."""

    @router.get("/admin", response_class=_s.HTMLResponse)
    def admin_dashboard(
        request: _s.Request,
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
        center_posts_page: int = 1,
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        return _s.templates.TemplateResponse(
            request,
            "admin.html",
            build_admin_dashboard_template_context(
                db=db,
                user=user,
                msg=msg,
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
            ),
        )

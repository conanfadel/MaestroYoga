"""Small HTML fragments for HTMX (lazy sections on admin pages)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .. import impl_state as _s
from .admin_dashboard_blocks import build_loyalty_public_and_trash_rows, load_trash_users_page


def _query_params_dict(request: _s.Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in request.query_params.multi_items():
        if k not in out:
            out[k] = v
    return out


def _trash_fragment_urls(qp: dict[str, str], safe_page: int, total_pages: int) -> tuple[str | None, str | None]:
    prev_url = None
    if safe_page > 1:
        n = dict(qp)
        n[_s.ADMIN_QP_TRASH_PAGE] = str(safe_page - 1)
        prev_url = _s._url_with_params("/admin/fragments/trash-users", **n)
    next_url = None
    if safe_page < total_pages:
        n = dict(qp)
        n[_s.ADMIN_QP_TRASH_PAGE] = str(safe_page + 1)
        next_url = _s._url_with_params("/admin/fragments/trash-users", **n)
    return prev_url, next_url


def register_admin_html_fragment_routes(router: APIRouter) -> None:
    @router.get("/admin/fragments/trash-users", response_class=_s.HTMLResponse)
    def admin_fragment_trash_users(request: _s.Request, db: _s.Session = _s.Depends(_s.get_db)):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return HTMLResponse(
                '<p class="small">انتهت الجلسة. أعد تحميل الصفحة.</p>',
                status_code=401,
            )
        assert user is not None
        if not _s.user_has_permission(user, "public_users.manage"):
            return HTMLResponse("", status_code=403)

        cid = _s.require_user_center_id(user)
        center = db.get(_s.models.Center, cid)
        qp = _query_params_dict(request)
        trash_q = (qp.get(_s.ADMIN_QP_TRASH_Q) or "").strip()
        try:
            trash_page = max(1, int(qp.get(_s.ADMIN_QP_TRASH_PAGE) or "1"))
        except ValueError:
            trash_page = 1

        trash_b = load_trash_users_page(db, cid, trash_q, trash_page, _s.ADMIN_PUBLIC_USERS_PAGE_SIZE)
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

        _pub_rows, trash_user_rows = build_loyalty_public_and_trash_rows(
            [],
            trash_b.trash_users_list,
            loyalty_by_email,
            center,
            subscription_number_by_email=subscription_number_by_email,
        )

        prev_url, next_url = _trash_fragment_urls(qp, trash_b.safe_trash_page, trash_b.trash_total_pages)

        trash_pagination: dict[str, Any] = {
            "page": trash_b.safe_trash_page,
            "page_size": _s.ADMIN_PUBLIC_USERS_PAGE_SIZE,
            "total": trash_b.trash_total,
            "total_pages": trash_b.trash_total_pages,
            "has_prev": trash_b.safe_trash_page > 1,
            "has_next": trash_b.safe_trash_page < trash_b.trash_total_pages,
            "prev_url": prev_url,
            "next_url": next_url,
        }

        return _s.templates.TemplateResponse(
            request,
            "partials/admin_fragment_trash_users_block.html",
            {
                "trash_users": trash_user_rows,
                "trash_pagination": trash_pagination,
            },
        )

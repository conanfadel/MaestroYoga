"""Admin org: toggle public user active / email-verified."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_org_public_users_toggle_routes(router: APIRouter) -> None:
    @router.post("/admin/public-users/toggle-active")
    def admin_toggle_public_user_active(
        request: _s.Request,
        public_user_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        cid = _s.require_user_center_id(user)
        if not _s.user_has_permission(user, "public_users.manage"):
            return _s._trainer_forbidden_redirect(return_section)
        row, redirect = _s._get_public_user_or_redirect(
            db, cid, public_user_id, scroll_y, return_section=return_section
        )
        if redirect:
            return redirect
        assert row is not None
        row.is_active = not row.is_active
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)

    @router.post("/admin/public-users/toggle-verified")
    def admin_toggle_public_user_verified(
        request: _s.Request,
        public_user_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        cid = _s.require_user_center_id(user)
        if not _s.user_has_permission(user, "public_users.manage"):
            return _s._trainer_forbidden_redirect(return_section)
        row, redirect = _s._get_public_user_or_redirect(
            db, cid, public_user_id, scroll_y, return_section=return_section
        )
        if redirect:
            return redirect
        assert row is not None
        row.email_verified = not row.email_verified
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)

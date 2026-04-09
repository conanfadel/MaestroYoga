"""Admin org: bulk actions on public users."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_org_public_users_bulk_routes(router: APIRouter) -> None:
    @router.post("/admin/public-users/bulk-action")
    def admin_public_users_bulk_action(
        request: _s.Request,
        action: str = _s.Form(...),
        public_user_ids: list[int] = _s.Form(default=[]),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        admin_user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert admin_user is not None
        if not _s.user_has_permission(admin_user, "public_users.manage"):
            return _s._trainer_forbidden_redirect(return_section)
        cid = _s.require_user_center_id(admin_user)
        ids = sorted(set(public_user_ids))
        if not ids:
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USERS_NONE_SELECTED, scroll_y, return_section)
        rows = _s._public_users_query_for_center(db, cid).filter(_s.models.PublicUser.id.in_(ids)).all()
        if not rows:
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_NOT_FOUND, scroll_y, return_section)

        action_key = action.strip().lower()
        if action_key not in _s.PUBLIC_USER_BULK_ACTIONS:
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USERS_BULK_INVALID_ACTION, scroll_y, return_section)
        if action_key == "resend_verification":
            sample_ok, _ = _s.validate_mailer_settings()
            if not sample_ok:
                return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED, scroll_y, return_section)

        updated = 0
        queued = 0
        for row in rows:
            row_updated, row_queued = _s._apply_public_user_bulk_action(db, action_key, row, request)
            updated += row_updated
            queued += row_queued
        db.commit()
        _s.log_security_event(
            "admin_public_users_bulk_action",
            request,
            "success",
            email=admin_user.email,
            details={"action": action_key, "selected": len(ids), "updated": updated, "queued": queued},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USERS_BULK_DONE, scroll_y, return_section)

"""Admin org: Public user moderation and bulk actions."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_org_public_users_routes(router: APIRouter) -> None:
    """Public user moderation and bulk actions."""

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
    
    
    @router.post("/admin/public-users/delete")
    def admin_delete_public_user(
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
        deleted_email, deleted_phone = _s._soft_delete_public_user(row)
        db.commit()
        _s.log_security_event(
            "admin_public_user_delete",
            request,
            "success",
            email=user.email,
            details={
                "deleted_public_user_id": public_user_id,
                "deleted_email": deleted_email,
                "deleted_phone": deleted_phone,
                "mode": "soft_delete",
            },
        )
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_DELETED, scroll_y, return_section)
    
    
    @router.post("/admin/public-users/resend-verification")
    def admin_resend_public_user_verification(
        request: _s.Request,
        public_user_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        admin_user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert admin_user is not None
        cid = _s.require_user_center_id(admin_user)
        if not _s.user_has_permission(admin_user, "public_users.manage"):
            return _s._trainer_forbidden_redirect(return_section)
        row, redirect = _s._get_public_user_or_redirect(
            db, cid, public_user_id, scroll_y, return_section=return_section
        )
        if redirect:
            return redirect
        assert row is not None
        if row.email_verified:
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_ALREADY_VERIFIED, scroll_y, return_section)
    
        queued, mail_info = _s.queue_verify_email_for_user(request, row)
        if not queued:
            _s.log_security_event(
                "admin_public_user_resend_verification",
                request,
                "mail_failed",
                email=admin_user.email,
                details={
                    "target_user_id": row.id,
                    "target_email": row.email,
                    "mail_error": mail_info[:200],
                },
            )
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_VERIFICATION_MAIL_FAILED, scroll_y, return_section)
    
        row.verification_sent_at = _s.utcnow_naive()
        db.commit()
        _s.log_security_event(
            "admin_public_user_resend_verification",
            request,
            "success",
            email=admin_user.email,
            details={"target_user_id": row.id, "target_email": row.email, "mail_status": "queued"},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_VERIFICATION_RESENT, scroll_y, return_section)
    
    
    @router.post("/admin/public-users/restore")
    def admin_restore_public_user(
        request: _s.Request,
        public_user_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        admin_user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert admin_user is not None
        cid = _s.require_user_center_id(admin_user)
        if not _s.user_has_permission(admin_user, "public_users.manage"):
            return _s._trainer_forbidden_redirect(return_section)
        row, redirect = _s._get_public_user_or_redirect(
            db, cid, public_user_id, scroll_y, allow_deleted=True, return_section=return_section
        )
        if redirect:
            return redirect
        assert row is not None
        if not row.is_deleted:
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_UPDATED, scroll_y, return_section)
        row.is_deleted = False
        row.deleted_at = None
        row.is_active = True
        db.commit()
        _s.log_security_event(
            "admin_public_user_restore",
            request,
            "success",
            email=admin_user.email,
            details={"restored_public_user_id": row.id, "restored_email": row.email},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_RESTORED, scroll_y, return_section)
    
    
    @router.post("/admin/public-users/permanent-delete")
    def admin_permanent_delete_public_user(
        request: _s.Request,
        public_user_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        admin_user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert admin_user is not None
        cid = _s.require_user_center_id(admin_user)
        if not _s.user_has_permission(admin_user, "public_users.manage"):
            return _s._trainer_forbidden_redirect(return_section)
        row, redirect = _s._get_public_user_or_redirect(
            db, cid, public_user_id, scroll_y, allow_deleted=True, return_section=return_section
        )
        if redirect:
            return redirect
        assert row is not None
        if not row.is_deleted:
            return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETE_FORBIDDEN, scroll_y, return_section)
        uid = row.id
        tomb_email = row.email
        db.delete(row)
        db.commit()
        _s.log_security_event(
            "admin_public_user_permanent_delete",
            request,
            "success",
            email=admin_user.email,
            details={"target_public_user_id": uid, "tombstone_email": tomb_email},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_PUBLIC_USER_PERMANENT_DELETED, scroll_y, return_section)
    
    
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
            # Fast fail if SMTP settings are invalid.
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
    
    

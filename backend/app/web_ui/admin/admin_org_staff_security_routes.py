"""Admin org: Staff invite and IP block/unblock."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_admin_org_staff_security_routes(router: APIRouter) -> None:
    """Staff invite and IP block/unblock."""

    @router.post("/admin/staff/create")
    def admin_create_staff_user(
        request: _s.Request,
        full_name: str = _s.Form(...),
        email: str = _s.Form(...),
        password: str = _s.Form(...),
        role: str = _s.Form(...),
        custom_role_label: str = _s.Form(default=""),
        permissions: list[str] = _s.Form(default_factory=list),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form("section-staff-invite"),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if user.role != "center_owner":
            return _s._admin_redirect(_s.ADMIN_MSG_STAFF_NOT_OWNER, scroll_y, return_section)
    
        role_s = (role or "").strip()
        try:
            payload = _s.schemas.UserCreateByOwner(
                full_name=(full_name or "").strip(),
                email=(email or "").strip(),
                password=password or "",
                role=role_s,
                custom_role_label=(custom_role_label or "").strip() or None,
                permission_ids=list(permissions) if role_s == "custom_staff" else None,
            )
        except _s.ValidationError:
            return _s._admin_redirect(_s.ADMIN_MSG_STAFF_INVALID, scroll_y, return_section)
    
        exists = db.query(_s.models.User).filter(_s.models.User.email == payload.email.lower()).first()
        if exists:
            return _s._admin_redirect(_s.ADMIN_MSG_STAFF_EMAIL_EXISTS, scroll_y, return_section)
    
        cid = _s.require_user_center_id(user)
        perm_json: str | None = None
        if payload.role == "custom_staff" and payload.permission_ids:
            perm_json = _s.json.dumps(payload.permission_ids, ensure_ascii=False)
        new_user = _s.models.User(
            center_id=cid,
            full_name=payload.full_name,
            email=payload.email.lower(),
            password_hash=_s.hash_password(payload.password),
            role=payload.role,
            custom_role_label=payload.custom_role_label if payload.role == "custom_staff" else None,
            permissions_json=perm_json,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        _s.log_security_event(
            "admin_staff_user_created",
            request,
            "success",
            email=user.email,
            details={"new_user_id": new_user.id, "new_role": new_user.role, "target_email": new_user.email},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_STAFF_CREATED, scroll_y, return_section)
    
    
    @router.post("/admin/security/ip-block")
    def admin_block_ip(
        request: _s.Request,
        ip: str = _s.Form(...),
        minutes: int = _s.Form(_s.ADMIN_IP_BLOCK_DEFAULT_MINUTES),
        reason: str = _s.Form("manual_block"),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not _s.user_has_permission(user, "security.audit"):
            return _s._security_owner_forbidden_redirect(return_section)
    
        target_ip = ip.strip()
        if not target_ip:
            return _s._admin_redirect(_s.ADMIN_MSG_IP_BLOCK_INVALID, return_section=return_section)
        if minutes <= 0:
            minutes = _s.ADMIN_IP_BLOCK_DEFAULT_MINUTES
        if minutes > _s.ADMIN_IP_BLOCK_MAX_MINUTES:
            minutes = _s.ADMIN_IP_BLOCK_MAX_MINUTES
        blocked_until = _s.utcnow_naive() + _s.timedelta(minutes=minutes)
    
        row = db.query(_s.models.BlockedIP).filter(_s.models.BlockedIP.ip == target_ip).first()
        if not row:
            row = _s.models.BlockedIP(
                ip=target_ip,
                reason=reason[:255],
                blocked_until=blocked_until,
                is_active=True,
            )
            db.add(row)
        else:
            row.reason = reason[:255]
            row.blocked_until = blocked_until
            row.is_active = True
        db.commit()
        _s.log_security_event(
            "admin_ip_block",
            request,
            "success",
            email=user.email,
            details={"target_ip": target_ip, "minutes": minutes, "reason": reason[:255]},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_IP_BLOCKED, return_section=return_section)
    
    
    @router.post("/admin/security/ip-unblock")
    def admin_unblock_ip(
        request: _s.Request,
        ip: str = _s.Form(...),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        user, redirect = _s._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not _s.user_has_permission(user, "security.audit"):
            return _s._security_owner_forbidden_redirect(return_section)
        target_ip = ip.strip()
        if not target_ip:
            return _s._admin_redirect(_s.ADMIN_MSG_IP_BLOCK_INVALID, return_section=return_section)
        row = db.query(_s.models.BlockedIP).filter(_s.models.BlockedIP.ip == target_ip).first()
        if not row:
            return _s._admin_redirect(_s.ADMIN_MSG_IP_UNBLOCK_NOT_FOUND, return_section=return_section)
        row.is_active = False
        db.commit()
        _s.log_security_event(
            "admin_ip_unblock",
            request,
            "success",
            email=user.email,
            details={"target_ip": target_ip, "reason": "manual_unblock"},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_IP_UNBLOCKED, return_section=return_section)
    
    

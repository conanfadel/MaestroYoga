"""Staff, security, public users, rooms, sessions, plans, FAQ CRUD."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_org_routes(router: APIRouter) -> None:
    """Organization and content management POST handlers."""

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
    
    
    @router.post("/admin/rooms")
    def admin_create_room(
        name: str = _s.Form(...),
        capacity: int = _s.Form(10),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("rooms.manage")),
    ):
        cid = _s.require_user_center_id(user)
        room = _s.models.Room(center_id=cid, name=name, capacity=capacity)
        db.add(room)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_ROOM_CREATED, scroll_y, return_section)
    
    
    @router.post("/admin/rooms/update")
    def admin_update_room(
        room_id: int = _s.Form(...),
        name: str = _s.Form(...),
        capacity: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("rooms.manage")),
    ):
        cid = _s.require_user_center_id(user)
        room = db.get(_s.models.Room, room_id)
        if not room or room.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Room not found")
        if capacity <= 0:
            return _s._admin_redirect(_s.ADMIN_MSG_ROOM_CAPACITY_INVALID, scroll_y, return_section)
        room.name = name.strip() or room.name
        room.capacity = capacity
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_ROOM_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/rooms/delete")
    def admin_delete_room(
        room_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("rooms.manage")),
    ):
        cid = _s.require_user_center_id(user)
        room = db.get(_s.models.Room, room_id)
        if not room or room.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Room not found")
    
        room_sessions = (
            db.query(_s.models.YogaSession)
            .filter(_s.models.YogaSession.center_id == cid, _s.models.YogaSession.room_id == room_id)
            .all()
        )
        if room_sessions:
            session_ids = [s.id for s in room_sessions]
            has_bookings = (
                db.query(_s.models.Booking.id)
                .filter(_s.models.Booking.center_id == cid, _s.models.Booking.session_id.in_(session_ids))
                .first()
            )
            if has_bookings:
                return _s._admin_redirect(_s.ADMIN_MSG_ROOM_HAS_BOOKINGS, scroll_y, return_section)
            for session in room_sessions:
                db.delete(session)
    
        db.delete(room)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_ROOM_DELETED, scroll_y, return_section)
    
    
    @router.post("/admin/rooms/delete-bulk")
    def admin_delete_rooms_bulk(
        room_ids: list[int] = _s.Form(default=[]),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("rooms.manage")),
    ):
        cid = _s.require_user_center_id(user)
        selected_ids = sorted(set(room_ids))
        if not selected_ids:
            return _s._admin_redirect(_s.ADMIN_MSG_ROOMS_NONE_SELECTED, scroll_y, return_section)
    
        rooms = (
            db.query(_s.models.Room)
            .filter(_s.models.Room.center_id == cid, _s.models.Room.id.in_(selected_ids))
            .all()
        )
        if not rooms:
            return _s._admin_redirect(_s.ADMIN_MSG_ROOMS_NOT_FOUND, scroll_y, return_section)
    
        room_ids = [r.id for r in rooms]
        all_sessions = (
            db.query(_s.models.YogaSession)
            .filter(_s.models.YogaSession.center_id == cid, _s.models.YogaSession.room_id.in_(room_ids))
            .all()
        )
        sessions_by_room: dict[int, list[_s.models.YogaSession]] = {}
        session_ids: list[int] = []
        for session in all_sessions:
            sessions_by_room.setdefault(session.room_id, []).append(session)
            session_ids.append(session.id)
        booked_session_ids: set[int] = set()
        if session_ids:
            booked_session_ids = {
                sid
                for (sid,) in db.query(_s.models.Booking.session_id)
                .filter(_s.models.Booking.center_id == cid, _s.models.Booking.session_id.in_(session_ids))
                .distinct()
                .all()
            }
    
        blocked_bookings = 0
        deleted = 0
        for room in rooms:
            room_sessions = sessions_by_room.get(room.id, [])
            if room_sessions:
                if any(s.id in booked_session_ids for s in room_sessions):
                    blocked_bookings += 1
                    continue
                for session in room_sessions:
                    db.delete(session)
            db.delete(room)
            deleted += 1
        db.commit()
    
        if deleted > 0 and blocked_bookings > 0:
            return _s._admin_redirect(_s.ADMIN_MSG_ROOMS_DELETED_PARTIAL_BOOKINGS, scroll_y, return_section)
        if deleted > 0:
            return _s._admin_redirect(_s.ADMIN_MSG_ROOMS_DELETED, scroll_y, return_section)
        if blocked_bookings > 0:
            return _s._admin_redirect(_s.ADMIN_MSG_ROOMS_DELETE_HAS_BOOKINGS, scroll_y, return_section)
        return _s._admin_redirect(_s.ADMIN_MSG_ROOMS_DELETE_BLOCKED, scroll_y, return_section)
    
    
    @router.post("/admin/sessions")
    def admin_create_session(
        room_id: int = _s.Form(...),
        title: str = _s.Form(...),
        trainer_name: str = _s.Form(...),
        level: str = _s.Form(...),
        starts_at: str = _s.Form(...),
        duration_minutes: int = _s.Form(60),
        price_drop_in: float = _s.Form(0.0),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("sessions.manage")),
    ):
        cid = _s.require_user_center_id(user)
        room = db.get(_s.models.Room, room_id)
        if not room or room.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Room not found")
    
        try:
            start_dt = _s.datetime.fromisoformat(starts_at)
        except ValueError:
            start_dt = _s.datetime.strptime(starts_at, "%Y-%m-%dT%H:%M")
    
        yoga_session = _s.models.YogaSession(
            center_id=cid,
            room_id=room_id,
            title=title,
            trainer_name=trainer_name,
            level=level,
            starts_at=start_dt,
            duration_minutes=duration_minutes,
            price_drop_in=float(price_drop_in),
        )
        db.add(yoga_session)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_SESSION_CREATED, scroll_y, return_section)
    
    
    @router.post("/admin/sessions/delete")
    def admin_delete_session(
        session_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("sessions.manage")),
    ):
        cid = _s.require_user_center_id(user)
        yoga_session = db.get(_s.models.YogaSession, session_id)
        if not yoga_session or yoga_session.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Session not found")
    
        booking_ids = [b.id for b in db.query(_s.models.Booking).filter(_s.models.Booking.session_id == session_id).all()]
        if booking_ids:
            db.query(_s.models.Payment).filter(_s.models.Payment.booking_id.in_(booking_ids)).delete(
                synchronize_session=False
            )
        db.query(_s.models.Booking).filter(_s.models.Booking.session_id == session_id).delete()
        db.delete(yoga_session)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_SESSION_DELETED, scroll_y, return_section)
    
    
    @router.post("/admin/plans")
    def admin_create_plan(
        name: str = _s.Form(...),
        plan_type: str = _s.Form(...),
        price: float = _s.Form(...),
        session_limit: str = _s.Form(default=""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        if plan_type not in ("weekly", "monthly", "yearly"):
            raise _s.HTTPException(status_code=400, detail="Invalid plan type")
        if price < 0:
            raise _s.HTTPException(status_code=400, detail="Price must be non-negative")
        parsed_session_limit = None
        if session_limit.strip():
            try:
                parsed_session_limit = int(session_limit)
            except ValueError:
                raise _s.HTTPException(status_code=400, detail="Session limit must be an integer")
            if parsed_session_limit <= 0:
                parsed_session_limit = None
        plan = _s.models.SubscriptionPlan(
            center_id=cid,
            name=name,
            plan_type=plan_type,
            price=price,
            session_limit=parsed_session_limit,
            is_active=True,
        )
        db.add(plan)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_CREATED, scroll_y, return_section)
    
    
    @router.post("/admin/plans/update-name")
    def admin_update_plan_name(
        plan_id: int = _s.Form(...),
        name: str = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        plan = db.get(_s.models.SubscriptionPlan, plan_id)
        if not plan or plan.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Plan not found")
        new_name = name.strip()
        if not new_name:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_NAME_INVALID, scroll_y, return_section)
        plan.name = new_name
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/plans/update-details")
    def admin_update_plan_details(
        plan_id: int = _s.Form(...),
        plan_type: str = _s.Form(...),
        price: float = _s.Form(...),
        session_limit: str = _s.Form(default=""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        plan = db.get(_s.models.SubscriptionPlan, plan_id)
        if not plan or plan.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Plan not found")
    
        plan_type_clean = plan_type.strip().lower()
        if plan_type_clean not in ("weekly", "monthly", "yearly"):
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
        if price < 0:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
    
        parsed_session_limit = None
        if session_limit.strip():
            try:
                parsed_session_limit = int(session_limit)
            except ValueError:
                return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
            if parsed_session_limit <= 0:
                return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_INVALID, scroll_y, return_section)
    
        plan.plan_type = plan_type_clean
        plan.price = float(price)
        plan.session_limit = parsed_session_limit
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DETAILS_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/plans/delete")
    def admin_delete_plan(
        plan_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("plans.manage")),
    ):
        cid = _s.require_user_center_id(user)
        plan = db.get(_s.models.SubscriptionPlan, plan_id)
        if not plan or plan.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Plan not found")
        has_subscriptions = db.query(_s.models.ClientSubscription).filter(_s.models.ClientSubscription.plan_id == plan_id).first()
        if has_subscriptions:
            return _s._admin_redirect(_s.ADMIN_MSG_PLAN_HAS_SUBSCRIPTIONS, scroll_y, return_section)
        db.delete(plan)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_PLAN_DELETED, scroll_y, return_section)
    
    
    @router.post("/admin/faqs")
    def admin_create_faq(
        question: str = _s.Form(...),
        answer: str = _s.Form(...),
        sort_order: int = _s.Form(0),
        is_active: str = _s.Form("1"),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        q = question.strip()
        a = answer.strip()
        if not q or not a:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
        row = _s.models.FAQItem(
            center_id=cid,
            question=q,
            answer=a,
            sort_order=max(0, int(sort_order)),
            is_active=is_active in {"1", "true", "on", "yes"},
        )
        db.add(row)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_CREATED, scroll_y, return_section)
    
    
    @router.post("/admin/faqs/update")
    def admin_update_faq(
        faq_id: int = _s.Form(...),
        question: str = _s.Form(...),
        answer: str = _s.Form(...),
        sort_order: int = _s.Form(0),
        is_active: str = _s.Form("1"),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        row = db.get(_s.models.FAQItem, faq_id)
        if not row or row.center_id != cid:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
        q = question.strip()
        a = answer.strip()
        if not q or not a:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_INVALID, scroll_y, return_section)
        row.question = q
        row.answer = a
        row.sort_order = max(0, int(sort_order))
        row.is_active = is_active in {"1", "true", "on", "yes"}
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/faqs/delete")
    def admin_delete_faq(
        faq_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        row = db.get(_s.models.FAQItem, faq_id)
        if not row or row.center_id != cid:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_NOT_FOUND, scroll_y, return_section)
        db.delete(row)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_DELETED, scroll_y, return_section)
    
    
    @router.post("/admin/faqs/reorder")
    def admin_reorder_faqs(
        ordered_ids_csv: str = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.faq")),
    ):
        cid = _s.require_user_center_id(user)
        raw = [x.strip() for x in ordered_ids_csv.split(",") if x.strip()]
        if not raw:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
        try:
            ids = [int(x) for x in raw]
        except ValueError:
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
        unique_ids = list(dict.fromkeys(ids))
        rows = (
            db.query(_s.models.FAQItem)
            .filter(_s.models.FAQItem.center_id == cid, _s.models.FAQItem.id.in_(unique_ids))
            .all()
        )
        if len(rows) != len(unique_ids):
            return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDER_INVALID, scroll_y, return_section)
        row_by_id = {r.id: r for r in rows}
        for idx, faq_id in enumerate(unique_ids, start=1):
            row_by_id[faq_id].sort_order = idx
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_FAQ_REORDERED, scroll_y, return_section)

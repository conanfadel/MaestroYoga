"""Admin org: Yoga session create/delete."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_admin_org_sessions_routes(router: APIRouter) -> None:
    """Yoga session create/delete."""

    @router.post("/admin/sessions")
    def admin_create_session(
        room_id: int = _s.Form(...),
        title: str = _s.Form(...),
        trainer_name: str = _s.Form(...),
        level: str = _s.Form(...),
        starts_at: str = _s.Form(...),
        duration_minutes: int = _s.Form(60),
        list_price: str = _s.Form(...),
        discount_mode: str = _s.Form(default="none"),
        discount_percent: str = _s.Form(default=""),
        reduced_price: str = _s.Form(default=""),
        discount_schedule_type: str = _s.Form(default="always"),
        discount_valid_from: str = _s.Form(default=""),
        discount_valid_until: str = _s.Form(default=""),
        discount_hour_start: str = _s.Form(default=""),
        discount_hour_end: str = _s.Form(default=""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("sessions.manage")),
    ):
        cid = _s.require_user_center_id(user)
        room = db.get(_s.models.Room, room_id)
        if not room or room.center_id != cid:
            raise _s.HTTPException(status_code=404, detail="Room not found")

        parsed, err = _s.discount_pricing.parse_admin_discount_pricing(
            list_price_raw=list_price,
            discount_mode_raw=discount_mode,
            discount_percent_raw=discount_percent,
            reduced_price_raw=reduced_price,
        )
        if err or not parsed:
            return _s._admin_redirect(_s.ADMIN_MSG_SESSION_PRICING_INVALID, scroll_y, return_section)

        sch, serr = _s.discount_pricing.parse_admin_discount_schedule(
            discount_mode=parsed.discount_mode,
            schedule_type_raw=discount_schedule_type,
            valid_from_raw=discount_valid_from,
            valid_until_raw=discount_valid_until,
            hour_start_raw=discount_hour_start,
            hour_end_raw=discount_hour_end,
        )
        if serr or not sch:
            return _s._admin_redirect(_s.ADMIN_MSG_SESSION_PRICING_INVALID, scroll_y, return_section)

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
            price_drop_in=float(parsed.effective_price),
            list_price=float(parsed.list_price),
            discount_mode=parsed.discount_mode,
            discount_percent=parsed.discount_percent,
            discount_schedule_type=sch.schedule_type,
            discount_valid_from=sch.valid_from,
            discount_valid_until=sch.valid_until,
            discount_hour_start=sch.hour_start,
            discount_hour_end=sch.hour_end,
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
    
    

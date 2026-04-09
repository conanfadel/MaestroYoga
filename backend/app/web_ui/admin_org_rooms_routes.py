"""Admin org: Room CRUD and bulk delete."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_org_rooms_routes(router: APIRouter) -> None:
    """Room CRUD and bulk delete."""

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
    
    

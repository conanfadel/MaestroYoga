"""Centers, clients, plans, rooms, sessions, and bookings CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import deps as _d


def register_routes(router: APIRouter) -> None:
    @router.post("/centers", response_model=_d.schemas.CenterOut)
    def create_center(
        payload: _d.schemas.CenterCreate,
        db: Session = Depends(_d.get_db),
        _: _d.models.User = Depends(_d.require_roles("superadmin")),
    ):
        center = _d.models.Center(**payload.model_dump())
        db.add(center)
        db.commit()
        db.refresh(center)
        return center

    @router.get("/centers", response_model=list[_d.schemas.CenterOut])
    def list_centers(
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.get_current_user),
    ):
        if user.role == "superadmin":
            return db.query(_d.models.Center).all()
        center_id = _d.require_user_center_id(user)
        center = db.get(_d.models.Center, center_id)
        return [center] if center else []

    @router.post("/clients", response_model=_d.schemas.ClientOut)
    def create_client(
        payload: _d.schemas.ClientCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_permissions("clients.manage")),
    ):
        client = _d.models.Client(center_id=_d.require_user_center_id(user), **payload.model_dump())
        db.add(client)
        db.commit()
        db.refresh(client)
        return client

    @router.get("/clients", response_model=list[_d.schemas.ClientOut])
    def list_clients(
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("clients.manage")),
    ):
        return (
            db.query(_d.models.Client)
            .filter(_d.models.Client.center_id == _d.require_user_center_id(user))
            .all()
        )

    @router.post("/plans", response_model=_d.schemas.SubscriptionPlanOut)
    def create_plan(
        payload: _d.schemas.SubscriptionPlanCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_permissions("plans.manage")),
    ):
        plan = _d.models.SubscriptionPlan(center_id=_d.require_user_center_id(user), **payload.model_dump())
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return plan

    @router.get("/plans", response_model=list[_d.schemas.SubscriptionPlanOut])
    def list_plans(
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("plans.manage", "sessions.manage")),
    ):
        return (
            db.query(_d.models.SubscriptionPlan)
            .filter(_d.models.SubscriptionPlan.center_id == _d.require_user_center_id(user))
            .all()
        )

    @router.post("/rooms", response_model=_d.schemas.RoomOut)
    def create_room(
        payload: _d.schemas.RoomCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_permissions("rooms.manage")),
    ):
        room = _d.models.Room(center_id=_d.require_user_center_id(user), **payload.model_dump())
        db.add(room)
        db.commit()
        db.refresh(room)
        return room

    @router.post("/sessions", response_model=_d.schemas.YogaSessionOut)
    def create_session(
        payload: _d.schemas.YogaSessionCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_permissions("sessions.manage")),
    ):
        center_id = _d.require_user_center_id(user)
        room = db.get(_d.models.Room, payload.room_id)
        if not room or room.center_id != center_id:
            raise HTTPException(status_code=404, detail="Room not found for center")
        yoga_session = _d.models.YogaSession(center_id=center_id, **payload.model_dump())
        db.add(yoga_session)
        db.commit()
        db.refresh(yoga_session)
        return yoga_session

    @router.get("/sessions", response_model=list[_d.schemas.YogaSessionOut])
    def list_sessions(
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(
            _d.require_any_permission("sessions.manage", "plans.manage", "reports.financial")
        ),
    ):
        return (
            db.query(_d.models.YogaSession)
            .filter(_d.models.YogaSession.center_id == _d.require_user_center_id(user))
            .all()
        )

    @router.post("/bookings", response_model=_d.schemas.BookingOut)
    def create_booking(
        payload: _d.schemas.BookingCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(
            _d.require_any_permission("sessions.manage", "clients.manage", "public_users.manage")
        ),
    ):
        center_id = _d.require_user_center_id(user)
        session = db.get(_d.models.YogaSession, payload.session_id)
        client = db.get(_d.models.Client, payload.client_id)
        if not session or not client:
            raise HTTPException(status_code=404, detail="Session or client not found")
        if session.center_id != center_id or client.center_id != center_id:
            raise HTTPException(status_code=400, detail="Center mismatch")

        room = db.get(_d.models.Room, session.room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found for session")
        if _d.count_active_bookings(db, session.id) >= room.capacity:
            raise HTTPException(status_code=400, detail="Room is full")

        booking = _d.models.Booking(center_id=center_id, **payload.model_dump(), status="confirmed")
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking

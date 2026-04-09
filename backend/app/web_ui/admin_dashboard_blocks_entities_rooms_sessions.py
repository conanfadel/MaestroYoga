"""Rooms, plans, FAQ loading and paginated yoga sessions for the admin dashboard."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks_pagination import normalize_admin_list_page

_SESSION_LEVEL_LABELS = {
    "beginner": "مبتدئ",
    "intermediate": "متوسط",
    "advanced": "متقدم",
}
_PLAN_TYPE_LABELS = {
    "weekly": "أسبوعي",
    "monthly": "شهري",
    "yearly": "سنوي",
}


@dataclass(frozen=True)
class RoomsPlansFaqBundle:
    rooms: list[Any]
    plans: list[Any]
    faqs: list[Any]
    rooms_by_id: dict[int, Any]
    room_sort_key: str
    room_ordering: dict[str, Any]


def load_rooms_plans_faqs(db: _s.Session, cid: int, room_sort: str) -> RoomsPlansFaqBundle:
    room_sort_key = (room_sort or "id_asc").strip().lower()
    room_ordering = {
        "id_asc": (_s.models.Room.id.asc(),),
        "name": (_s.models.Room.name.asc(), _s.models.Room.id.asc()),
        "newest": (_s.models.Room.id.desc(),),
        "capacity_desc": (_s.models.Room.capacity.desc(), _s.models.Room.name.asc(), _s.models.Room.id.asc()),
        "capacity_asc": (_s.models.Room.capacity.asc(), _s.models.Room.name.asc(), _s.models.Room.id.asc()),
    }
    if room_sort_key in {"sessions_desc", "sessions_asc"}:
        session_count_order = (
            _s.func.count(_s.models.YogaSession.id).desc()
            if room_sort_key == "sessions_desc"
            else _s.func.count(_s.models.YogaSession.id).asc()
        )
        rooms = (
            db.query(_s.models.Room)
            .outerjoin(
                _s.models.YogaSession,
                _s.and_(
                    _s.models.YogaSession.room_id == _s.models.Room.id,
                    _s.models.YogaSession.center_id == cid,
                ),
            )
            .filter(_s.models.Room.center_id == cid)
            .group_by(_s.models.Room.id)
            .order_by(session_count_order, _s.models.Room.name.asc(), _s.models.Room.id.asc())
            .all()
        )
    else:
        room_order_by = room_ordering.get(room_sort_key, room_ordering["id_asc"])
        rooms = (
            db.query(_s.models.Room)
            .filter(_s.models.Room.center_id == cid)
            .order_by(*room_order_by)
            .all()
        )
    plans = (
        db.query(_s.models.SubscriptionPlan)
        .filter(_s.models.SubscriptionPlan.center_id == cid)
        .order_by(_s.models.SubscriptionPlan.price.asc())
        .all()
    )
    faqs = (
        db.query(_s.models.FAQItem)
        .filter(_s.models.FAQItem.center_id == cid)
        .order_by(_s.models.FAQItem.sort_order.asc(), _s.models.FAQItem.created_at.asc())
        .all()
    )
    rooms_by_id = {r.id: r for r in rooms}
    return RoomsPlansFaqBundle(
        rooms=rooms,
        plans=plans,
        faqs=faqs,
        rooms_by_id=rooms_by_id,
        room_sort_key=room_sort_key,
        room_ordering=room_ordering,
    )


@dataclass(frozen=True)
class SessionPageBundle:
    sessions: list[Any]
    sessions_total: int
    safe_sessions_page: int
    sessions_total_pages: int
    sessions_page_size: int
    session_rows: list[dict[str, Any]]


def load_paginated_session_rows(
    db: _s.Session, cid: int, rooms_by_id: dict[int, Any], sessions_page: int
) -> SessionPageBundle:
    sessions_page_size = _s.ADMIN_SESSIONS_PAGE_SIZE
    sessions_base_query = db.query(_s.models.YogaSession).filter(_s.models.YogaSession.center_id == cid)
    sessions_total = sessions_base_query.order_by(None).count()
    safe_sessions_page, sessions_total_pages, sessions_offset = normalize_admin_list_page(
        sessions_page,
        sessions_total,
        sessions_page_size,
    )
    sessions = (
        sessions_base_query.order_by(_s.models.YogaSession.starts_at.desc())
        .offset(sessions_offset)
        .limit(sessions_page_size)
        .all()
    )
    session_ids_page = [int(s.id) for s in sessions]
    spots_by_session_page = _s._spots_available_map(db, cid, session_ids_page)
    now_for_sessions = _s.utcnow_naive()
    session_rows: list[dict[str, Any]] = []
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        session_rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": _SESSION_LEVEL_LABELS.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _s._fmt_dt(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "room_id": s.room_id,
                "spots_available": spots_by_session_page.get(int(s.id), 0),
                "capacity": room.capacity if room else 0,
                "is_past": bool(s.starts_at < now_for_sessions),
            }
        )
    return SessionPageBundle(
        sessions=sessions,
        sessions_total=sessions_total,
        safe_sessions_page=safe_sessions_page,
        sessions_total_pages=sessions_total_pages,
        sessions_page_size=sessions_page_size,
        session_rows=session_rows,
    )


def plan_rows_from_plans(plans: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "plan_type": p.plan_type,
            "plan_type_label": _PLAN_TYPE_LABELS.get(p.plan_type, p.plan_type),
            "price": p.price,
            "session_limit": p.session_limit,
            "is_active": p.is_active,
        }
        for p in plans
    ]


def faq_rows_from_faqs(faqs: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": f.id,
            "question": f.question,
            "answer": f.answer,
            "sort_order": f.sort_order,
            "is_active": f.is_active,
        }
        for f in faqs
    ]

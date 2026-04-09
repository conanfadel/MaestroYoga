"""Rooms, sessions, users, payments, loyalty rows, and center posts for the admin dashboard."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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


@dataclass(frozen=True)
class PublicUsersPageBundle:
    public_users: list[Any]
    public_users_total: int
    safe_public_user_page: int
    public_users_total_pages: int
    public_users_page_size: int
    status_key: str
    verified_key: str


def load_filtered_public_users_page(
    db: _s.Session,
    cid: int,
    public_user_q: str,
    public_user_status: str,
    public_user_verified: str,
    public_user_page: int,
) -> PublicUsersPageBundle:
    public_users_query = _s._public_users_query_for_center(db, cid)
    q = public_user_q.strip()
    if q:
        public_users_query = public_users_query.filter(
            _s.or_(
                _s.models.PublicUser.full_name.ilike(f"%{q}%"),
                _s.models.PublicUser.email.ilike(f"%{q}%"),
                _s.models.PublicUser.phone.ilike(f"%{q}%"),
            )
        )
    status_key = public_user_status.strip().lower() or "active"
    if status_key == "deleted":
        public_users_query = public_users_query.filter(_s.models.PublicUser.is_deleted.is_(True))
    elif status_key == "inactive":
        public_users_query = public_users_query.filter(
            _s.models.PublicUser.is_deleted.is_(False), _s.models.PublicUser.is_active.is_(False)
        )
    else:
        public_users_query = public_users_query.filter(
            _s.models.PublicUser.is_deleted.is_(False), _s.models.PublicUser.is_active.is_(True)
        )
    verified_key = public_user_verified.strip().lower()
    if verified_key == "verified":
        public_users_query = public_users_query.filter(_s.models.PublicUser.email_verified.is_(True))
    elif verified_key == "unverified":
        public_users_query = public_users_query.filter(_s.models.PublicUser.email_verified.is_(False))
    public_users_page_size = _s.ADMIN_PUBLIC_USERS_PAGE_SIZE
    public_users_total = public_users_query.order_by(None).count()
    safe_public_user_page, public_users_total_pages, public_users_offset = normalize_admin_list_page(
        public_user_page,
        public_users_total,
        public_users_page_size,
    )
    public_users = (
        public_users_query.order_by(_s.models.PublicUser.created_at.desc())
        .offset(public_users_offset)
        .limit(public_users_page_size)
        .all()
    )
    return PublicUsersPageBundle(
        public_users=public_users,
        public_users_total=public_users_total,
        safe_public_user_page=safe_public_user_page,
        public_users_total_pages=public_users_total_pages,
        public_users_page_size=public_users_page_size,
        status_key=status_key,
        verified_key=verified_key,
    )


@dataclass(frozen=True)
class TrashUsersPageBundle:
    trash_users_list: list[Any]
    trash_total: int
    safe_trash_page: int
    trash_total_pages: int


def load_trash_users_page(
    db: _s.Session, cid: int, trash_q: str, trash_page: int, page_size: int
) -> TrashUsersPageBundle:
    trash_q_s = trash_q.strip()
    trash_base = _s._public_users_query_for_center(db, cid).filter(_s.models.PublicUser.is_deleted.is_(True))
    if trash_q_s:
        trash_base = trash_base.filter(
            _s.or_(
                _s.models.PublicUser.full_name.ilike(f"%{trash_q_s}%"),
                _s.models.PublicUser.email.ilike(f"%{trash_q_s}%"),
            )
        )
    trash_total = trash_base.order_by(None).count()
    safe_trash_page, trash_total_pages, trash_offset = normalize_admin_list_page(
        trash_page,
        trash_total,
        page_size,
    )
    trash_users_list = (
        trash_base.order_by(_s.models.PublicUser.deleted_at.desc(), _s.models.PublicUser.id.desc())
        .offset(trash_offset)
        .limit(page_size)
        .all()
    )
    return TrashUsersPageBundle(
        trash_users_list=trash_users_list,
        trash_total=trash_total,
        safe_trash_page=safe_trash_page,
        trash_total_pages=trash_total_pages,
    )


def build_dashboard_summary_dict(
    db: _s.Session,
    cid: int,
    rooms: Sequence[Any],
    sessions_total: int,
    plans: Sequence[Any],
    paid_revenue_total: float,
    paid_revenue_today: float,
    public_users_count: int,
    public_users_deleted_count: int,
    public_users_new_7d: int,
) -> dict[str, Any]:
    return {
        "rooms_count": len(rooms),
        "sessions_count": sessions_total,
        "bookings_count": db.query(_s.models.Booking).filter(_s.models.Booking.center_id == cid).count(),
        "clients_count": db.query(_s.models.Client).filter(_s.models.Client.center_id == cid).count(),
        "active_plans_count": sum(1 for p in plans if p.is_active),
        "active_subscriptions_count": (
            db.query(_s.models.ClientSubscription)
            .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
            .filter(
                _s.models.Client.center_id == cid,
                _s.models.ClientSubscription.status == "active",
            )
            .count()
        ),
        "revenue_total": float(paid_revenue_total or 0.0),
        "revenue_today": float(paid_revenue_today or 0.0),
        "public_users_count": int(public_users_count) - int(public_users_deleted_count),
        "public_users_deleted_count": int(public_users_deleted_count),
        "public_users_new_7d": int(public_users_new_7d),
    }


@dataclass(frozen=True)
class PaymentsPageBundle:
    payment_rows: list[dict[str, Any]]
    payments_total: int
    safe_payments_page: int
    payments_total_pages: int
    payments_page_size: int


def load_paginated_payment_rows(
    db: _s.Session,
    cid: int,
    payment_from_dt: Any,
    payment_to_dt: Any,
    payments_page: int,
) -> PaymentsPageBundle:
    payments_page_size = _s.ADMIN_PAYMENTS_PAGE_SIZE
    payments_base_query = db.query(_s.models.Payment).filter(_s.models.Payment.center_id == cid)
    if payment_from_dt:
        payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) >= payment_from_dt)
    if payment_to_dt:
        payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) <= payment_to_dt)
    payments_total = payments_base_query.order_by(None).count()
    safe_payments_page, payments_total_pages, payments_offset = normalize_admin_list_page(
        payments_page,
        payments_total,
        payments_page_size,
    )
    recent_payments = (
        payments_base_query.order_by(_s.models.Payment.paid_at.desc())
        .offset(payments_offset)
        .limit(payments_page_size)
        .all()
    )
    client_ids = [p.client_id for p in recent_payments]
    clients_by_id = {
        c.id: c
        for c in db.query(_s.models.Client).filter(_s.models.Client.id.in_(client_ids)).all()
    }
    status_labels = {
        "paid": "مدفوع",
        "pending": "قيد الانتظار",
        "failed": "فشل",
    }
    payment_rows = []
    for pay in recent_payments:
        client = clients_by_id.get(pay.client_id)
        payment_rows.append(
            {
                "id": pay.id,
                "client_name": client.full_name if client else f"عميل #{pay.client_id}",
                "payment_method": pay.payment_method,
                "amount": pay.amount,
                "currency": pay.currency,
                "status": pay.status,
                "status_label": status_labels.get(pay.status, pay.status),
                "paid_at_display": _s._fmt_dt(pay.paid_at),
            }
        )
    return PaymentsPageBundle(
        payment_rows=payment_rows,
        payments_total=payments_total,
        safe_payments_page=safe_payments_page,
        payments_total_pages=payments_total_pages,
        payments_page_size=payments_page_size,
    )


def build_loyalty_public_and_trash_rows(
    public_users: Sequence[Any],
    trash_users_list: Sequence[Any],
    loyalty_by_email: dict[str, int],
    center: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public_user_rows: list[dict[str, Any]] = []
    for u in public_users:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = _s.loyalty_context_for_count(cnt, center=center)
        public_user_rows.append(
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": _s._phone_admin_display(u.phone),
                "is_active": u.is_active,
                "email_verified": u.email_verified,
                "is_deleted": bool(u.is_deleted),
                "created_at_display": _s._fmt_dt(u.created_at),
                "loyalty_confirmed_count": cnt,
                "loyalty_tier": lt["loyalty_tier"],
                "loyalty_tier_label": lt["loyalty_tier_label"],
            }
        )
    trash_user_rows: list[dict[str, Any]] = []
    for u in trash_users_list:
        cnt = loyalty_by_email.get((u.email or "").lower(), 0)
        lt = _s.loyalty_context_for_count(cnt, center=center)
        trash_user_rows.append(
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": _s._phone_admin_display(u.phone),
                "deleted_at_display": _s._fmt_dt(u.deleted_at),
                "created_at_display": _s._fmt_dt(u.created_at),
                "loyalty_confirmed_count": cnt,
                "loyalty_tier": lt["loyalty_tier"],
                "loyalty_tier_label": lt["loyalty_tier_label"],
            }
        )
    return public_user_rows, trash_user_rows


@dataclass(frozen=True)
class CenterPostsBundle:
    center_post_admin_rows: list[dict[str, Any]]
    editing_post: dict[str, Any] | None
    center_post_type_choices: list[dict[str, str]]
    safe_post_edit: int
    safe_center_posts_page: int
    center_posts_total: int
    center_posts_total_pages: int
    center_posts_page_size: int


def load_center_posts_admin_section(
    db: _s.Session,
    cid: int,
    center_posts_page: int,
    post_edit: int,
    post_edit_url: Callable[[int], str],
) -> CenterPostsBundle:
    safe_post_edit = max(0, int(post_edit or 0))
    center_posts_page_size = _s.ADMIN_CENTER_POSTS_PAGE_SIZE
    center_posts_base_query = (
        db.query(_s.models.CenterPost)
        .filter(_s.models.CenterPost.center_id == cid)
        .order_by(_s.models.CenterPost.updated_at.desc())
    )
    center_posts_total = center_posts_base_query.order_by(None).count()
    safe_center_posts_page, center_posts_total_pages, center_posts_offset = normalize_admin_list_page(
        center_posts_page,
        center_posts_total,
        center_posts_page_size,
    )
    center_posts_all = (
        center_posts_base_query.offset(center_posts_offset).limit(center_posts_page_size).all()
    )
    center_post_ids_page = [int(cp.id) for cp in center_posts_all]
    center_post_gallery_counts = {
        int(pid): int(cnt)
        for pid, cnt in (
            db.query(_s.models.CenterPostImage.post_id, _s.func.count(_s.models.CenterPostImage.id))
            .filter(_s.models.CenterPostImage.post_id.in_(center_post_ids_page))
            .group_by(_s.models.CenterPostImage.post_id)
            .all()
        )
    } if center_post_ids_page else {}

    center_post_admin_rows: list[dict[str, Any]] = []
    for cp in center_posts_all:
        center_post_admin_rows.append(
            {
                "id": cp.id,
                "title": cp.title,
                "post_type": cp.post_type,
                "type_label": _s.CENTER_POST_TYPE_LABELS.get(cp.post_type, cp.post_type),
                "is_published": cp.is_published,
                "is_pinned": cp.is_pinned,
                "updated_display": _s._fmt_dt(cp.updated_at),
                "gallery_count": center_post_gallery_counts.get(int(cp.id), 0),
                "public_url": _s._url_with_params("/post", center_id=str(cid), post_id=str(cp.id))
                if cp.is_published
                else "",
                "edit_url": post_edit_url(cp.id),
            }
        )

    editing_post: dict[str, Any] | None = None
    if safe_post_edit:
        ep = db.get(_s.models.CenterPost, safe_post_edit)
        if ep and ep.center_id == cid:
            gi = sorted(ep.images, key=lambda x: (x.sort_order, x.id))
            editing_post = {
                "id": ep.id,
                "title": ep.title,
                "summary": ep.summary or "",
                "body": ep.body or "",
                "post_type": ep.post_type,
                "is_pinned": ep.is_pinned,
                "is_published": ep.is_published,
                "cover_image_url": ep.cover_image_url or "",
                "gallery": [{"id": g.id, "url": g.image_url} for g in gi],
            }

    center_post_type_choices = [
        {"value": k, "label": v} for k, v in sorted(_s.CENTER_POST_TYPE_LABELS.items(), key=lambda x: x[1])
    ]

    return CenterPostsBundle(
        center_post_admin_rows=center_post_admin_rows,
        editing_post=editing_post,
        center_post_type_choices=center_post_type_choices,
        safe_post_edit=safe_post_edit,
        safe_center_posts_page=safe_center_posts_page,
        center_posts_total=center_posts_total,
        center_posts_total_pages=center_posts_total_pages,
        center_posts_page_size=center_posts_page_size,
    )

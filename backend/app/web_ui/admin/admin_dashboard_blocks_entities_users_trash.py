"""Public users, trash list, and loyalty row shaping for the admin dashboard."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .. import impl_state as _s
from .admin_dashboard_blocks_pagination import normalize_admin_list_page


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

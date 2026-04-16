"""Public user queries tied to a center, spots map, and bulk admin actions."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models


def _public_user_has_client_at_center_exists(db: Session, center_id: int):
    """EXISTS مرتبط: عميل في المركز بنفس بريد المستخدم (بعد trim وبدون حساسية لحالة الأحرف)."""
    email_pub = func.lower(func.trim(models.PublicUser.email))
    email_cli = func.lower(func.trim(models.Client.email))
    return (
        db.query(models.Client.id)
        .filter(
            models.Client.center_id == center_id,
            email_cli == email_pub,
        )
        .exists()
    )
from ...booking_utils import ACTIVE_BOOKING_STATUSES
from ...client_numbering import ensure_client_subscription_number, next_client_subscription_number
from ...public_auth_helpers import queue_verify_email_for_user
from ...time_utils import utcnow_naive
from ...web_shared import public_center_id_str_from_next
from ._constants import GA4_MEASUREMENT_ID


def _public_users_query_for_center(db: Session, center_id: int):
    return db.query(models.PublicUser).filter(_public_user_has_client_at_center_exists(db, center_id))


def _ensure_client_for_public_register(db: Session, user: models.PublicUser, next_url: str) -> None:
    """Create or refresh a Client row for the center in ``next`` so the user appears in admin public-user lists."""
    cid_str = public_center_id_str_from_next(next_url)
    try:
        center_id = int(cid_str)
    except (ValueError, TypeError):
        return
    if not db.get(models.Center, center_id):
        return
    existing = (
        db.query(models.Client)
        .filter(
            models.Client.center_id == center_id,
            func.lower(models.Client.email) == func.lower(user.email),
        )
        .first()
    )
    if existing:
        existing.full_name = user.full_name
        if user.phone:
            existing.phone = user.phone
        ensure_client_subscription_number(db, client=existing)
        return
    db.add(
        models.Client(
            center_id=center_id,
            full_name=user.full_name,
            email=user.email.lower(),
            phone=user.phone,
            subscription_number=next_client_subscription_number(db, center_id=center_id),
        )
    )


def _spots_available_map(db: Session, center_id: int, session_ids: list[int]) -> dict[int, int]:
    if not session_ids:
        return {}
    sessions = (
        db.query(models.YogaSession.id, models.YogaSession.room_id)
        .filter(models.YogaSession.center_id == center_id, models.YogaSession.id.in_(session_ids))
        .all()
    )
    if not sessions:
        return {}
    room_ids = sorted({rid for _, rid in sessions if rid is not None})
    rooms = (
        db.query(models.Room.id, models.Room.capacity)
        .filter(models.Room.center_id == center_id, models.Room.id.in_(room_ids))
        .all()
        if room_ids
        else []
    )
    capacity_by_room = {int(rid): int(cap or 0) for rid, cap in rooms}
    booking_counts = {
        int(sid): int(cnt)
        for sid, cnt in (
            db.query(models.Booking.session_id, func.count(models.Booking.id))
            .filter(
                models.Booking.session_id.in_(session_ids),
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .group_by(models.Booking.session_id)
            .all()
        )
    }
    out: dict[int, int] = {}
    for sid, rid in sessions:
        cap = capacity_by_room.get(int(rid), 0) if rid is not None else 0
        active = booking_counts.get(int(sid), 0)
        out[int(sid)] = max(0, cap - active)
    return out


def _soft_delete_public_user(row: models.PublicUser) -> tuple[str, str]:
    original_email = row.email
    original_phone = row.phone or ""
    tombstone = f"deleted+{row.id}+{int(utcnow_naive().timestamp())}@maestroyoga.local"
    row.email = tombstone
    row.phone = None
    row.is_active = False
    row.email_verified = False
    row.is_deleted = True
    if row.deleted_at is None:
        row.deleted_at = utcnow_naive()
    return original_email, original_phone


def _apply_public_user_bulk_action(
    db: Session, action_key: str, row: models.PublicUser, request: Request
) -> tuple[int, int]:
    updated = 0
    queued = 0
    if action_key == "activate" and not row.is_deleted:
        row.is_active = True
        updated = 1
    elif action_key == "deactivate" and not row.is_deleted:
        row.is_active = False
        updated = 1
    elif action_key == "verify" and not row.is_deleted:
        row.email_verified = True
        updated = 1
    elif action_key == "unverify" and not row.is_deleted:
        row.email_verified = False
        updated = 1
    elif action_key == "resend_verification" and (not row.is_deleted) and (not row.email_verified):
        ok, _ = queue_verify_email_for_user(request, row)
        if ok:
            row.verification_sent_at = utcnow_naive()
            queued = 1
    elif action_key == "soft_delete" and not row.is_deleted:
        _soft_delete_public_user(row)
        updated = 1
    elif action_key == "restore" and row.is_deleted:
        row.is_deleted = False
        row.deleted_at = None
        row.is_active = True
        updated = 1
    elif action_key == "permanent_delete" and row.is_deleted:
        db.delete(row)
        updated = 1
    return updated, queued


def _analytics_context(page_name: str, **extra: str) -> dict:
    data = {
        "ga4_measurement_id": GA4_MEASUREMENT_ID,
        "analytics_enabled": bool(GA4_MEASUREMENT_ID),
        "analytics_page_name": page_name,
    }
    data.update(extra)
    return data

"""حجز جلسة ضمن حصة اشتراك نشط (حد جلسات في الخطة) دون دفع منفصل."""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models
from .booking_utils import ACTIVE_BOOKING_STATUSES
from .public_session_visibility import (
    yoga_session_accepts_new_public_booking,
    yoga_session_still_on_public_schedule,
)
from .public_subscription_helpers import count_confirmed_plan_sessions_in_period, get_active_subscription_bundle


def confirm_public_plan_session_booking(
    db: Session,
    *,
    center_id: int,
    session_id: int,
    client: models.Client,
    models_module: type,
    utcnow_fn,
    count_active_bookings_fn,
    integrity_error_cls: type,
) -> tuple[bool, str]:
    """يُنشئ حجزاً مؤكداً ودفعة صفرية ضمن الخطة. يرجع (نجاح، رمز_رسالة)."""
    now = utcnow_fn()
    bundle = get_active_subscription_bundle(db, center_id=center_id, client_id=client.id, now=now)
    if not bundle:
        return False, "plan_booking_no_subscription"
    sub, plan = bundle
    sub_locked = (
        db.query(models_module.ClientSubscription)
        .filter(models_module.ClientSubscription.id == sub.id)
        .with_for_update()
        .first()
    )
    if not sub_locked:
        return False, "plan_booking_no_subscription"

    limit_v = plan.session_limit
    if limit_v is None or int(limit_v) <= 0:
        return False, "plan_booking_no_cap"

    yoga_session = db.get(models_module.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != center_id:
        return False, "cart_invalid"
    if not yoga_session_still_on_public_schedule(yoga_session, now=now):
        return False, "session_ended"
    if not yoga_session_accepts_new_public_booking(yoga_session, now=now):
        return False, "session_started"

    room = db.get(models_module.Room, yoga_session.room_id)
    if not room:
        return False, "full"
    if max(0, int(room.capacity or 0) - count_active_bookings_fn(db, yoga_session.id)) <= 0:
        return False, "full"

    dup = (
        db.query(models_module.Booking)
        .filter(
            models_module.Booking.session_id == session_id,
            models_module.Booking.client_id == client.id,
            models_module.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .first()
    )
    if dup:
        return False, "duplicate"

    used = count_confirmed_plan_sessions_in_period(
        db, client_id=client.id, center_id=center_id, subscription=sub_locked
    )
    if used >= int(limit_v):
        return False, "plan_sessions_exhausted"

    booking = models_module.Booking(
        center_id=center_id,
        session_id=session_id,
        client_id=client.id,
        status="confirmed",
        booked_at=now,
    )
    db.add(booking)
    db.flush()
    payment = models_module.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=booking.id,
        amount=0.0,
        currency="SAR",
        payment_method="plan_sessions_included",
        status="paid",
        paid_at=now,
        created_at=now,
    )
    db.add(payment)
    try:
        db.commit()
    except integrity_error_cls:
        db.rollback()
        return False, "duplicate"
    return True, "plan_booked"

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


def session_ids_booked_via_plan_for_client(
    db: Session,
    *,
    center_id: int,
    client_id: int,
    session_ids: list[int],
) -> set[int]:
    """معرفات الجلسات التي للعميل حجز مؤكد مرتبط بدفع «ضمن الخطة»."""
    if not session_ids:
        return set()
    rows = (
        db.query(models.Booking.session_id)
        .join(models.Payment, models.Payment.booking_id == models.Booking.id)
        .filter(
            models.Booking.client_id == client_id,
            models.Booking.center_id == center_id,
            models.Booking.status == "confirmed",
            models.Booking.session_id.in_(session_ids),
            models.Payment.payment_method == "plan_sessions_included",
        )
        .distinct()
        .all()
    )
    out: set[int] = set()
    for (sid,) in rows:
        if sid is not None:
            out.add(int(sid))
    return out


def cancel_public_plan_session_booking(
    db: Session,
    *,
    center_id: int,
    session_id: int,
    client: models.Client,
    models_module: type,
    utcnow_fn,
) -> tuple[bool, str]:
    """يُلغي حجزاً مؤكداً ضمن الخطة قبل بدء الجلسة. يرجع (نجاح، رمز_رسالة)."""
    now = utcnow_fn()
    B = models_module.Booking
    P = models_module.Payment
    booking = (
        db.query(B)
        .join(P, P.booking_id == B.id)
        .filter(
            B.client_id == client.id,
            B.center_id == center_id,
            B.session_id == session_id,
            B.status == "confirmed",
            P.payment_method == "plan_sessions_included",
            P.status == "paid",
        )
        .first()
    )
    if not booking:
        return False, "plan_cancel_not_found"

    yoga_session = db.get(models_module.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != center_id:
        return False, "plan_cancel_not_found"
    if not yoga_session_accepts_new_public_booking(yoga_session, now=now):
        return False, "plan_cancel_session_started"

    booking.status = "cancelled"
    for pay in (
        db.query(models_module.Payment)
        .filter(
            models_module.Payment.booking_id == booking.id,
            models_module.Payment.payment_method == "plan_sessions_included",
            models_module.Payment.status == "paid",
        )
        .all()
    ):
        pay.status = "failed"
    db.commit()
    return True, "plan_session_cancelled"


def confirm_public_plan_sessions_booking(
    db: Session,
    *,
    center_id: int,
    session_ids: list[int],
    client: models.Client,
    models_module: type,
    utcnow_fn,
    count_active_bookings_fn,
    integrity_error_cls: type,
) -> tuple[bool, str]:
    """يُنشئ حجوزات مؤكدة ودفعات صفرية ضمن حصة الخطة في معاملة واحدة (كلها أو لا شيء)."""
    now = utcnow_fn()
    ids = sorted({int(x) for x in session_ids if int(x) > 0})
    if not ids:
        return False, "plan_sessions_batch_none"
    if len(ids) > 40:
        return False, "plan_sessions_batch_too_many"

    bundle = get_active_subscription_bundle(db, center_id=center_id, client_id=client.id, now=now)
    if not bundle:
        latest_sub = (
            db.query(models_module.ClientSubscription)
            .join(models_module.SubscriptionPlan, models_module.SubscriptionPlan.id == models_module.ClientSubscription.plan_id)
            .filter(
                models_module.ClientSubscription.client_id == client.id,
                models_module.SubscriptionPlan.center_id == center_id,
            )
            .order_by(models_module.ClientSubscription.end_date.desc())
            .first()
        )
        if latest_sub and (str(latest_sub.status or "").lower() == "expired" or latest_sub.end_date < now):
            return False, "plan_subscription_expired"
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
    lim = int(limit_v)

    used = count_confirmed_plan_sessions_in_period(
        db, client_id=client.id, center_id=center_id, subscription=sub_locked
    )
    if used + len(ids) > lim:
        return False, "plan_sessions_exhausted"

    for session_id in ids:
        yoga_session = db.get(models_module.YogaSession, session_id)
        if not yoga_session or yoga_session.center_id != center_id:
            return False, "cart_invalid"
        if not yoga_session_still_on_public_schedule(yoga_session, now=now):
            return False, "session_ended"
        if not yoga_session_accepts_new_public_booking(yoga_session, now=now):
            return False, "session_started"
        sa = yoga_session.starts_at
        if sa is None or sa < sub_locked.start_date or sa > sub_locked.end_date:
            return False, "plan_booking_session_outside_period"
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

    for session_id in ids:
        yoga_session = db.get(models_module.YogaSession, session_id)
        if not yoga_session:
            return False, "cart_invalid"
        room = db.get(models_module.Room, yoga_session.room_id)
        if not room:
            return False, "full"
        if max(0, int(room.capacity or 0) - count_active_bookings_fn(db, yoga_session.id)) <= 0:
            return False, "full"
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
        db.flush()

    try:
        db.commit()
    except integrity_error_cls:
        db.rollback()
        return False, "duplicate"

    if used + len(ids) >= lim:
        return True, "plan_booked_quota_complete"
    if len(ids) == 1:
        return True, "plan_booked"
    return True, "plan_sessions_booked_batch"


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
    """يُنشئ حجزاً واحداً ضمن الخطة (يستدعي المسار المجمّع)."""
    return confirm_public_plan_sessions_booking(
        db,
        center_id=center_id,
        session_ids=[int(session_id)],
        client=client,
        models_module=models_module,
        utcnow_fn=utcnow_fn,
        count_active_bookings_fn=count_active_bookings_fn,
        integrity_error_cls=integrity_error_cls,
    )

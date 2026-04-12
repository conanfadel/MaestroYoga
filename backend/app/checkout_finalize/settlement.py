"""Apply paid/failed outcomes to payments, bookings, and subscriptions."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .. import models
from ..time_utils import utcnow_naive
from .metadata import collect_payments_from_metadata

logger = logging.getLogger(__name__)


def finalize_checkout_paid(db: Session, metadata: dict, provider_ref: str) -> None:
    payment_rows, subscription = collect_payments_from_metadata(db, metadata, provider_ref)
    changed = False
    now = utcnow_naive()
    newly_paid: list[models.Payment] = []
    prev_sub_status = subscription.status if subscription else None

    for payment in payment_rows:
        prev_status = payment.status
        if payment.status != "paid":
            payment.status = "paid"
            payment.paid_at = now
            changed = True
            if prev_status != "paid":
                newly_paid.append(payment)
        if payment.booking_id:
            booking = db.get(models.Booking, payment.booking_id)
            if booking and booking.status != "confirmed":
                booking.status = "confirmed"
                changed = True
        elif subscription and subscription.status != "active":
            subscription.status = "active"
            changed = True
    if subscription and not payment_rows and subscription.status == "pending":
        subscription.status = "active"
        changed = True
    if changed:
        db.commit()
        try:
            from .payment_notifications import dispatch_payment_success_notifications

            dispatch_payment_success_notifications(
                db,
                newly_paid_payments=newly_paid,
                subscription_prev_status=prev_sub_status,
                subscription=subscription,
            )
        except Exception:
            logger.exception("payment_success notification dispatch failed")


def finalize_checkout_failed(db: Session, metadata: dict, provider_ref: str) -> None:
    payment_rows, subscription = collect_payments_from_metadata(db, metadata, provider_ref)
    for payment in payment_rows:
        payment.status = "failed"
        if payment.booking_id:
            booking = db.get(models.Booking, payment.booking_id)
            if booking and booking.status == "pending_payment":
                booking.status = "cancelled"
    if subscription and subscription.status == "pending":
        subscription.status = "cancelled"
    if payment_rows or subscription:
        db.commit()

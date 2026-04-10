"""Apply paid/failed outcomes to payments, bookings, and subscriptions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from .metadata import collect_payments_from_metadata


def finalize_checkout_paid(db: Session, metadata: dict, provider_ref: str) -> None:
    payment_rows, subscription = collect_payments_from_metadata(db, metadata, provider_ref)
    changed = False
    for payment in payment_rows:
        if payment.status != "paid":
            payment.status = "paid"
            changed = True
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

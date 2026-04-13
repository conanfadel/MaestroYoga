"""Apply paid/failed/refunded/disputed outcomes to payments, bookings, and subscriptions."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .. import models
from ..time_utils import utcnow_naive
from .metadata import collect_payments_from_metadata

logger = logging.getLogger(__name__)


def _expected_amount_minor_sar(payment_rows: list[models.Payment]) -> int:
    total = sum(float(p.amount or 0) for p in payment_rows)
    return int(round(total * 100))


def _currency_matches(expected: str, got: str | None) -> bool:
    if not got:
        return True
    a = (expected or "sar").lower().strip()
    b = got.lower().strip()
    if a == b:
        return True
    if {a, b} <= {"sar", "sau"}:
        return True
    return False


def finalize_checkout_paid(
    db: Session,
    metadata: dict,
    provider_ref: str,
    *,
    amount_total_minor: int | None = None,
    currency_from_provider: str | None = None,
) -> None:
    payment_rows, subscription = collect_payments_from_metadata(db, metadata, provider_ref)
    if payment_rows and all(p.status == "paid" for p in payment_rows):
        return

    if amount_total_minor is not None and payment_rows:
        expected_minor = _expected_amount_minor_sar(payment_rows)
        cur = (payment_rows[0].currency or "SAR").strip()
        if not _currency_matches(cur, currency_from_provider):
            logger.error(
                "checkout amount verification: currency mismatch expected=%s got=%s provider_ref=%s",
                cur,
                currency_from_provider,
                provider_ref,
            )
            finalize_checkout_failed(db, metadata, provider_ref)
            return
        if abs(int(amount_total_minor) - expected_minor) > 1:
            logger.error(
                "checkout amount verification: minor mismatch expected=%s got=%s provider_ref=%s meta=%s",
                expected_minor,
                amount_total_minor,
                provider_ref,
                metadata,
            )
            finalize_checkout_failed(db, metadata, provider_ref)
            return

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


def finalize_payment_refunded(db: Session, metadata: dict, provider_ref: str = "") -> None:
    """Mark payments refunded and release bookings / subscriptions where applicable."""
    payment_rows, subscription = collect_payments_from_metadata(db, metadata, provider_ref)
    changed = False
    for payment in payment_rows:
        if payment.status == "refunded":
            continue
        if payment.status not in ("paid", "pending"):
            continue
        was_paid = payment.status == "paid"
        payment.status = "refunded"
        changed = True
        if payment.booking_id:
            booking = db.get(models.Booking, payment.booking_id)
            if booking and booking.status in ("confirmed", "pending_payment", "booked"):
                booking.status = "cancelled"
                changed = True
        elif (
            was_paid
            and subscription
            and subscription.status == "active"
            and not payment.booking_id
        ):
            subscription.status = "cancelled"
            changed = True
    if changed:
        db.commit()


def finalize_payment_disputed(db: Session, metadata: dict, provider_ref: str = "") -> None:
    """Record a card dispute on paid rows (does not cancel bookings automatically)."""
    payment_rows, _subscription = collect_payments_from_metadata(db, metadata, provider_ref)
    changed = False
    for payment in payment_rows:
        if payment.status == "disputed":
            continue
        if payment.status != "paid":
            continue
        payment.status = "disputed"
        changed = True
    if changed:
        db.commit()

"""إتمام حالة المدفوعات والحجوزات بعد نجاح/فشل الدفع (Stripe Checkout أو ميسر Invoice)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


def collect_payments_from_metadata(
    db: Session,
    metadata: dict,
    provider_ref: str,
) -> tuple[list[models.Payment], models.ClientSubscription | None]:
    """يجمع صفوف Payment من metadata أو من provider_ref."""
    payment_rows: list[models.Payment] = []
    meta = metadata or {}
    pids_raw = meta.get("payment_ids") or ""
    if pids_raw:
        for part in str(pids_raw).split(","):
            part = part.strip()
            if part.isdigit():
                pr = db.get(models.Payment, int(part))
                if pr:
                    payment_rows.append(pr)
    if not payment_rows:
        payment_id = meta.get("payment_id")
        if payment_id and str(payment_id).strip().isdigit():
            pr = db.get(models.Payment, int(str(payment_id).strip()))
            if pr:
                payment_rows.append(pr)
    if not payment_rows and provider_ref:
        lones = db.query(models.Payment).filter(models.Payment.provider_ref == provider_ref).all()
        payment_rows.extend(lones)
    subscription_id = meta.get("subscription_id")
    subscription: models.ClientSubscription | None = None
    if subscription_id and str(subscription_id).strip().isdigit():
        try:
            subscription = db.get(models.ClientSubscription, int(str(subscription_id).strip()))
        except (TypeError, ValueError):
            subscription = None
    return payment_rows, subscription


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

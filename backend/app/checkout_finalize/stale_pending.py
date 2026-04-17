"""Expire abandoned hosted checkouts: pending payments + pending_payment bookings."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import models
from ..time_utils import utcnow_naive

logger = logging.getLogger(__name__)


def expire_stale_pending_payments(db: Session, *, older_than_minutes: int) -> int:
    """
    Cancel bookings stuck in ``pending_payment`` and mark their ``Payment`` rows ``failed``
    when the checkout was never completed within the TTL.

    Also cancels **pending** subscriptions whose subscription checkout payment row is still
    ``pending`` (matched by center, client, plan price, and close timestamps).

    Returns the number of **payment** rows updated.
    """
    if older_than_minutes < 5:
        older_than_minutes = 5
    cutoff = utcnow_naive() - timedelta(minutes=older_than_minutes)
    n = 0

    rows = (
        db.query(models.Payment)
        .filter(
            models.Payment.status == "pending",
            models.Payment.created_at < cutoff,
            models.Payment.booking_id.isnot(None),
        )
        .order_by(models.Payment.id.asc())
        .limit(500)
        .all()
    )
    for pay in rows:
        booking = db.get(models.Booking, pay.booking_id) if pay.booking_id else None
        if not booking or booking.status != "pending_payment":
            continue
        pay.status = "failed"
        booking.status = "cancelled"
        n += 1

    orphan_payments = (
        db.query(models.Payment)
        .filter(
            models.Payment.status == "pending",
            models.Payment.created_at < cutoff,
            models.Payment.booking_id.is_(None),
        )
        .order_by(models.Payment.id.asc())
        .limit(200)
        .all()
    )
    for pay in orphan_payments:
        if not str(pay.payment_method or "").startswith("subscription_"):
            continue
        sub = (
            db.query(models.ClientSubscription)
            .join(models.SubscriptionPlan, models.SubscriptionPlan.id == models.ClientSubscription.plan_id)
            .filter(
                models.ClientSubscription.client_id == pay.client_id,
                models.ClientSubscription.status == "pending",
                models.SubscriptionPlan.center_id == pay.center_id,
            )
            .order_by(models.ClientSubscription.id.desc())
            .first()
        )
        if not sub:
            continue
        plan = db.get(models.SubscriptionPlan, sub.plan_id)
        if not plan:
            continue
        from ..discount_pricing import plan_public_checkout_amount

        expected = plan_public_checkout_amount(plan, now=pay.created_at) if pay.created_at else plan_public_checkout_amount(plan)
        if abs(float(expected) - float(pay.amount)) > 0.05:
            continue
        if sub.start_date and pay.created_at:
            delta = abs((sub.start_date - pay.created_at).total_seconds())
            if delta > 600:
                continue
        pay.status = "failed"
        sub.status = "cancelled"
        n += 1

    if n:
        db.commit()
        logger.info("expire_stale_pending_payments: updated %s payment row(s)", n)
    return n

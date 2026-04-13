"""Stripe and Paymob payment webhooks (mounted at app root)."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from .checkout_finalize import (
        finalize_checkout_failed,
        finalize_checkout_paid,
        finalize_payment_disputed,
        finalize_payment_refunded,
    )
    from .database import get_db
    from .payments import StripePaymentProvider
    from .payments.paymob_provider import metadata_from_paymob_obj, verify_paymob_processed_hmac
except ImportError:
    from backend.app.checkout_finalize import (
        finalize_checkout_failed,
        finalize_checkout_paid,
        finalize_payment_disputed,
        finalize_payment_refunded,
    )
    from backend.app.database import get_db
    from backend.app.payments import StripePaymentProvider
    from backend.app.payments.paymob_provider import metadata_from_paymob_obj, verify_paymob_processed_hmac

logger = logging.getLogger(__name__)

webhooks_router = APIRouter()


@webhooks_router.post("/payments/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()
    try:
        event = StripePaymentProvider.construct_event(payload, stripe_signature)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}") from exc

    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        session_id = event_data.get("id") or ""
        metadata = dict(event_data.get("metadata", {}) or {})
        amount_total = event_data.get("amount_total")
        currency = str(event_data.get("currency") or "").strip()
        amount_minor: int | None = None
        if amount_total is not None:
            try:
                amount_minor = int(amount_total)
            except (TypeError, ValueError):
                amount_minor = None
        finalize_checkout_paid(
            db,
            metadata,
            str(session_id),
            amount_total_minor=amount_minor,
            currency_from_provider=currency or None,
        )
    elif event_type == "checkout.session.expired":
        session_id = event_data.get("id") or ""
        metadata = dict(event_data.get("metadata", {}) or {})
        finalize_checkout_failed(db, metadata, str(session_id))
    elif event_type == "charge.refunded":
        ch = event_data if isinstance(event_data, dict) else {}
        meta = dict(ch.get("metadata") or {})
        finalize_payment_refunded(db, meta, str(ch.get("id") or ""))
    elif event_type == "charge.dispute.created":
        dispute = event_data if isinstance(event_data, dict) else {}
        ch_id = dispute.get("charge")
        meta: dict = {}
        if ch_id:
            sk = os.getenv("STRIPE_SECRET_KEY", "").strip()
            if sk:
                try:
                    import stripe

                    stripe.api_key = sk
                    ch = stripe.Charge.retrieve(str(ch_id))
                    md = getattr(ch, "metadata", None) or {}
                    meta = dict(md) if isinstance(md, dict) else {}
                except Exception:
                    logger.exception("dispute webhook: failed to retrieve charge %s", ch_id)
        finalize_payment_disputed(db, meta, str(ch_id or dispute.get("id") or ""))

    return {"received": True}


@webhooks_router.post("/payments/webhook/paymob")
async def paymob_transaction_webhook(request: Request, db: Session = Depends(get_db)):
    """إشعار Paymob (Transaction processed). يُفعَّل من لوحة Paymob → Webhooks."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    if not isinstance(payload, dict):
        return {"received": True}

    hmac_secret = os.getenv("PAYMOB_HMAC_SECRET", "").strip() or os.getenv("PAYMOB_HMAC", "").strip()
    received = str(payload.get("hmac") or payload.get("HMAC") or "").strip()
    if not hmac_secret or not received:
        logger.warning("paymob webhook missing PAYMOB_HMAC_SECRET (or PAYMOB_HMAC) or hmac in payload")
        raise HTTPException(status_code=400, detail="paymob hmac not configured")

    if not verify_paymob_processed_hmac(payload, received, hmac_secret):
        raise HTTPException(status_code=400, detail="invalid paymob hmac")

    obj = payload.get("obj")
    if not isinstance(obj, dict):
        return {"received": True}

    meta = metadata_from_paymob_obj(obj)
    order = obj.get("order")
    order_id = ""
    if isinstance(order, dict) and order.get("id") is not None:
        order_id = str(order.get("id"))
    if not order_id and obj.get("id") is not None:
        order_id = str(obj.get("id"))

    is_refunded = bool(obj.get("is_refunded"))
    if is_refunded:
        finalize_payment_refunded(db, meta, order_id)
        return {"received": True}

    success = bool(obj.get("success"))
    amount_cents = obj.get("amount_cents")
    amount_minor: int | None = None
    if amount_cents is not None:
        try:
            amount_minor = int(amount_cents)
        except (TypeError, ValueError):
            amount_minor = None
    currency = str(obj.get("currency") or "").strip()

    if success:
        finalize_checkout_paid(
            db,
            meta,
            order_id,
            amount_total_minor=amount_minor,
            currency_from_provider=currency or None,
        )
    else:
        finalize_checkout_failed(db, meta, order_id)
    return {"received": True}

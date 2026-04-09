"""Stripe and Moyasar payment webhooks (mounted at app root)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

try:
    from .checkout_finalize import finalize_checkout_failed, finalize_checkout_paid
    from .database import get_db
    from .main_rest_api import _moyasar_extract_invoice_id
    from .payments import MoyasarPaymentProvider, StripePaymentProvider
except ImportError:
    from backend.app.checkout_finalize import finalize_checkout_failed, finalize_checkout_paid
    from backend.app.database import get_db
    from backend.app.main_rest_api import _moyasar_extract_invoice_id
    from backend.app.payments import MoyasarPaymentProvider, StripePaymentProvider

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
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}")

    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        session_id = event_data.get("id") or ""
        metadata = dict(event_data.get("metadata", {}) or {})
        finalize_checkout_paid(db, metadata, str(session_id))
    elif event_type == "checkout.session.expired":
        session_id = event_data.get("id") or ""
        metadata = dict(event_data.get("metadata", {}) or {})
        finalize_checkout_failed(db, metadata, str(session_id))

    return {"received": True}


@webhooks_router.post("/payments/webhook/moyasar")
async def moyasar_invoice_webhook(request: Request, db: Session = Depends(get_db)):
    """إشعار ميسر عند دفع الفاتورة (callback_url). يُنصح بالتحقق عبر API."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    invoice_id = _moyasar_extract_invoice_id(payload)
    if not invoice_id:
        return {"received": True}
    try:
        fresh = MoyasarPaymentProvider.fetch_invoice(str(invoice_id))
    except Exception as exc:
        logger.warning("moyasar invoice fetch failed: %s", exc)
        return {"received": True}
    if fresh.get("status") != "paid":
        return {"received": True}
    meta = dict(fresh.get("metadata") or {})
    finalize_checkout_paid(db, meta, str(invoice_id))
    return {"received": True}

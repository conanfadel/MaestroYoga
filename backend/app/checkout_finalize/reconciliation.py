"""Background reconciliation and monitoring for pending checkout payments."""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any
from urllib import request as urllib_request

from sqlalchemy.orm import Session

from .. import models
from ..time_utils import utcnow_naive
from .settlement import finalize_checkout_failed, finalize_checkout_paid

logger = logging.getLogger(__name__)


def _meta_from_payment(payment: models.Payment) -> dict[str, str]:
    meta: dict[str, str] = {
        "payment_id": str(int(payment.id)),
        "center_id": str(int(payment.center_id)),
        "client_id": str(int(payment.client_id)),
    }
    if payment.booking_id:
        meta["booking_id"] = str(int(payment.booking_id))
    return meta


def reconcile_stale_pending_payments(
    db: Session,
    *,
    older_than_minutes: int = 5,
    max_rows: int = 100,
) -> dict[str, int]:
    """
    Reconcile stale pending payments by querying provider state when possible.

    Current active reconciliation is implemented for Stripe checkout sessions.
    """
    now = utcnow_naive()
    cutoff = now - timedelta(minutes=max(1, int(older_than_minutes)))
    rows = (
        db.query(models.Payment)
        .filter(
            models.Payment.status == "pending",
            models.Payment.created_at < cutoff,
            models.Payment.provider_ref.isnot(None),
        )
        .order_by(models.Payment.created_at.asc())
        .limit(max(1, int(max_rows)))
        .all()
    )
    if not rows:
        return {"examined": 0, "paid": 0, "failed": 0, "skipped": 0}

    paid_n = 0
    failed_n = 0
    skipped_n = 0
    provider_mode = os.getenv("PAYMENT_PROVIDER", "mock").strip().lower()

    for payment in rows:
        pref = str(payment.provider_ref or "").strip()
        if provider_mode != "stripe" or not pref.startswith("cs_"):
            skipped_n += 1
            continue
        try:
            import stripe

            sk = os.getenv("STRIPE_SECRET_KEY", "").strip()
            if not sk:
                skipped_n += 1
                continue
            stripe.api_key = sk
            session = stripe.checkout.Session.retrieve(pref)
            pay_status = str(getattr(session, "payment_status", "") or "").strip().lower()
            status = str(getattr(session, "status", "") or "").strip().lower()
            meta = _meta_from_payment(payment)
            if pay_status == "paid":
                finalize_checkout_paid(db, meta, pref)
                paid_n += 1
            elif status in {"expired", "complete"} and pay_status != "paid":
                finalize_checkout_failed(db, meta, pref)
                failed_n += 1
            else:
                skipped_n += 1
        except Exception:
            logger.exception("reconcile_stale_pending_payments failed for payment=%s", payment.id)
            skipped_n += 1

    return {"examined": len(rows), "paid": paid_n, "failed": failed_n, "skipped": skipped_n}


def monitor_delayed_webhook_payments(
    db: Session,
    *,
    overdue_minutes: int = 10,
    max_rows: int = 100,
) -> int:
    """
    Record operational alerts for pending payments waiting too long for finalization.
    """
    cutoff = utcnow_naive() - timedelta(minutes=max(1, int(overdue_minutes)))
    rows = (
        db.query(models.Payment)
        .filter(
            models.Payment.status == "pending",
            models.Payment.created_at < cutoff,
        )
        .order_by(models.Payment.created_at.asc())
        .limit(max(1, int(max_rows)))
        .all()
    )
    if not rows:
        return 0

    for payment in rows:
        details: dict[str, Any] = {
            "payment_id": int(payment.id),
            "center_id": int(payment.center_id),
            "provider_ref": str(payment.provider_ref or ""),
            "payment_method": str(payment.payment_method or ""),
            "created_at": str(payment.created_at),
            "alert_kind": "webhook_delay",
        }
        ev = models.SecurityAuditEvent(
            event_type="payment_webhook_delay",
            status="warning",
            path="/payments/webhook",
            details_json=json.dumps(details, ensure_ascii=True),
        )
        db.add(ev)
    db.commit()
    logger.warning("monitor_delayed_webhook_payments: %s overdue pending payment(s)", len(rows))
    return len(rows)


def send_operational_alert(*, title: str, body: str, count: int) -> bool:
    """
    Send external operational alert when configured.

    Env:
    - OPS_ALERT_WEBHOOK_URL
    - OPS_ALERT_WEBHOOK_TOKEN (optional, sent as Bearer)
    """
    url = os.getenv("OPS_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return False
    payload = {"title": title, "body": body, "count": int(count), "source": "maestroyoga"}
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = urllib_request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    token = os.getenv("OPS_ALERT_WEBHOOK_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib_request.urlopen(req, timeout=8) as resp:
            code = int(getattr(resp, "status", 200))
            return 200 <= code < 300
    except Exception:
        logger.exception("send_operational_alert failed")
        return False

"""Subscription lifecycle automation (expiry transitions)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from . import models
from .time_utils import utcnow_naive

logger = logging.getLogger(__name__)


def expire_active_subscriptions(db: Session, *, now: datetime | None = None, max_rows: int = 500) -> int:
    """Transition active subscriptions to expired when end_date is in the past."""
    now = now or utcnow_naive()
    rows = (
        db.query(models.ClientSubscription)
        .filter(
            models.ClientSubscription.status == "active",
            models.ClientSubscription.end_date < now,
        )
        .order_by(models.ClientSubscription.end_date.asc())
        .limit(max(1, int(max_rows)))
        .all()
    )
    if not rows:
        return 0

    for sub in rows:
        sub.status = "expired"
        details = {
            "subscription_id": int(sub.id),
            "client_id": int(sub.client_id),
            "plan_id": int(sub.plan_id),
            "end_date": str(sub.end_date),
        }
        db.add(
            models.SecurityAuditEvent(
                event_type="subscription_expired_auto",
                status="success",
                path="/internal/subscriptions/expiry",
                details_json=json.dumps(details, ensure_ascii=True),
            )
        )
    db.commit()
    logger.info("expire_active_subscriptions: expired %s subscription row(s)", len(rows))
    return len(rows)

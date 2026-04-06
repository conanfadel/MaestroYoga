"""تذكيرات بريدية قبل الجلسات (خلفية)."""

from __future__ import annotations

import logging
import os
from datetime import timedelta

from . import models
from .database import SessionLocal
from .mailer import queue_notification_email
from .time_utils import utcnow_naive

logger = logging.getLogger(__name__)


def run_session_reminders() -> int:
    """يرسل تذكيراً لمرة واحدة لكل حجز قبل الجلسة بعدد الساعات REMINDER_HOURS_BEFORE (افتراضي 24)."""
    if os.getenv("ENABLE_SESSION_REMINDERS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return 0
    try:
        hours = max(1, int(os.getenv("REMINDER_HOURS_BEFORE", "24")))
    except ValueError:
        hours = 24

    now = utcnow_naive()
    window_start = now + timedelta(hours=hours)
    window_end = now + timedelta(hours=hours + 1)

    db = SessionLocal()
    sent = 0
    try:
        q = (
            db.query(models.Booking, models.YogaSession, models.Client)
            .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
            .join(models.Client, models.Client.id == models.Booking.client_id)
            .filter(
                models.Booking.status.in_(("booked", "confirmed", "pending_payment")),
                models.YogaSession.starts_at >= window_start,
                models.YogaSession.starts_at < window_end,
            )
        )
        for booking, session, client in q.all():
            exists = (
                db.query(models.ReminderSent)
                .filter(
                    models.ReminderSent.booking_id == booking.id,
                    models.ReminderSent.kind == "session_upcoming",
                )
                .first()
            )
            if exists:
                continue
            center = db.get(models.Center, session.center_id)
            cname = center.name if center else str(session.center_id)
            st = session.starts_at.strftime("%Y-%m-%d %H:%M") if session.starts_at else ""
            subject = f"تذكير: جلسة «{session.title}»"
            body = (
                f"مرحباً {client.full_name},\n\n"
                f"تذكير: لديك حجز في جلسة «{session.title}» ({st}) في {cname}.\n\n"
                "نتمنى لك وقتاً ممتعاً."
            )
            ok, _ = queue_notification_email(client.email, subject, body)
            if ok:
                db.add(
                    models.ReminderSent(
                        booking_id=booking.id,
                        kind="session_upcoming",
                    )
                )
                sent += 1
        db.commit()
    except Exception as exc:
        logger.exception("session reminders failed: %s", exc)
        db.rollback()
    finally:
        db.close()
    return sent

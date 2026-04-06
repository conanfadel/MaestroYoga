"""قائمة انتظار الجلسات: إشعار أول منتظر عند توفر مكان."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from . import models
from .booking_utils import spots_available
from .mailer import queue_notification_email
from .time_utils import utcnow_naive

logger = logging.getLogger(__name__)


def _public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")


def notify_waitlist_slot_available(db: Session, session_id: int) -> None:
    """عند إلغاء حجز أو فشل دفع يحرر مكاناً: أرسل بريداً لأول منتظر وأزل سجل الانتظار."""
    session = db.get(models.YogaSession, session_id)
    if not session:
        return
    if spots_available(db, session) <= 0:
        return

    row = (
        db.query(models.SessionWaitlist)
        .filter(models.SessionWaitlist.session_id == session_id)
        .order_by(models.SessionWaitlist.created_at.asc())
        .first()
    )
    if not row:
        return

    pu = db.get(models.PublicUser, row.public_user_id)
    if not pu or pu.is_deleted:
        db.delete(row)
        db.commit()
        return

    base = _public_base_url()
    q = urlencode({"center_id": session.center_id, "session_id": session_id})
    link = f"{base}/index?{q}"
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    subject = f"{app_name} — مكان أصبح متاحاً في قائمة الانتظار"
    body = (
        f"مرحباً {pu.full_name},\n\n"
        f"أصبح هناك مكان متاح في جلسة «{session.title}».\n"
        f"سارع بالحجز من الصفحة:\n{link}\n\n"
        "إذا لم تعد ترغب بالحجز، يمكنك تجاهل هذه الرسالة."
    )
    ok, reason = queue_notification_email(pu.email, subject, body)
    if ok:
        row.notified_at = utcnow_naive()
        db.delete(row)
        db.commit()
        logger.info("waitlist notified session_id=%s public_user_id=%s", session_id, pu.id)
    else:
        logger.warning("waitlist email failed session_id=%s reason=%s", session_id, reason)


def notify_waitlist_for_sessions(db: Session, session_ids: set[int]) -> None:
    for sid in session_ids:
        try:
            notify_waitlist_slot_available(db, sid)
        except Exception as exc:
            logger.exception("waitlist notify failed session_id=%s: %s", sid, exc)

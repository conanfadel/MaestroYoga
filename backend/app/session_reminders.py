"""تذكيرات بريدية قبل الجلسات — للتشغيل عبر cron أو scripts/send_session_reminders.py."""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from . import models
from .mailer._core_send import send_mail
from .time_utils import utcnow_naive

logger = logging.getLogger(__name__)

REMINDER_KIND_24H = "24h"


def _state_path() -> Path:
    raw = os.getenv("SESSION_REMINDER_STATE_FILE", ".data/session_reminder_state.json").strip()
    return Path(raw)


def _load_sent_keys() -> set[str]:
    path = _state_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
    except (OSError, json.JSONDecodeError):
        logger.warning("session_reminder_state_read_failed path=%s", path)
    return set()


def _save_sent_keys(keys: set[str]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=0), encoding="utf-8")


def _reminder_key(booking_id: int, kind: str = REMINDER_KIND_24H) -> str:
    return f"{booking_id}:{kind}"


def _public_index_url(center_id: int) -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        return f"/index?center_id={center_id}"
    return f"{base}/index?center_id={center_id}"


def dispatch_session_reminder_emails(
    db: Session,
    *,
    hours_before: float = 24.0,
    window_minutes: float = 45.0,
) -> dict[str, int]:
    """
    يرسل بريد تذكير للحجوزات المؤكّدة التي تبدأ جلساتها خلال نافذة زمنية حول (الآن + hours_before).
    يُسجَّل الإرسال في ملف حالة لتجنّب التكرار (بدون عمود DB إضافي — مناسب للإطلاق السريع).
    """
    if os.getenv("DISABLE_SESSION_REMINDER_EMAIL", "").strip().lower() in ("1", "true", "yes"):
        return {"sent": 0, "skipped": 0, "errors": 0, "disabled": 1}

    now = utcnow_naive()
    target = now + timedelta(hours=hours_before)
    half = timedelta(minutes=window_minutes / 2.0)
    window_start = target - half
    window_end = target + half

    sent_keys = _load_sent_keys()
    stats = {"sent": 0, "skipped": 0, "errors": 0, "disabled": 0}

    rows = (
        db.query(models.Booking, models.YogaSession, models.Client, models.Center)
        .join(models.YogaSession, models.Booking.session_id == models.YogaSession.id)
        .join(models.Client, models.Booking.client_id == models.Client.id)
        .join(models.Center, models.Booking.center_id == models.Center.id)
        .filter(
            models.Booking.status == "confirmed",
            models.YogaSession.starts_at >= window_start,
            models.YogaSession.starts_at < window_end,
        )
        .all()
    )

    for booking, session, client, center in rows:
        key = _reminder_key(int(booking.id))
        if key in sent_keys:
            stats["skipped"] += 1
            continue
        to_email = (client.email or "").strip()
        if not to_email:
            stats["skipped"] += 1
            continue

        when_str = session.starts_at.strftime("%Y-%m-%d %H:%M") if session.starts_at else ""
        center_name = center.name if center else "المركز"
        index_url = _public_index_url(int(center.id))
        subject = f"تذكير: جلستك في {center_name} غداً"
        body = "\n".join(
            [
                f"مرحبًا {client.full_name}،",
                "",
                f"نذكّرك بجلستك: {session.title}",
                f"الموعد: {when_str}",
                f"المدرب/ة: {session.trainer_name or '—'}",
                "",
                f"للاطلاع على حجوزاتك: {index_url}",
                "",
                "مع تحيات فريق المركز",
            ]
        )
        ok, info = send_mail(to_email, subject, body)
        if ok:
            sent_keys.add(key)
            stats["sent"] += 1
            logger.info("session_reminder_sent booking_id=%s email=%s", booking.id, to_email)
        else:
            stats["errors"] += 1
            logger.warning(
                "session_reminder_failed booking_id=%s email=%s info=%s",
                booking.id,
                to_email,
                info[:200],
            )

    _save_sent_keys(sent_keys)
    return stats

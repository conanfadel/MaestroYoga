"""إشعارات FCM للجوال (أندرويد الآن، iOS لاحقاً عبر نفس Firebase)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from . import models
from .time_utils import utcnow_naive

logger = logging.getLogger(__name__)

_firebase_initialized: bool | None = None
_no_firebase_cred_logged = False
_firebase_import_failed = False


def _init_firebase() -> bool:
    """يعيد True إذا أصبح تطبيق Firebase جاهزاً للإرسال."""
    global _firebase_initialized, _no_firebase_cred_logged, _firebase_import_failed
    if _firebase_initialized is True:
        return True
    if _firebase_import_failed:
        return False
    path = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip() or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    ).strip()
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("firebase-admin not installed; FCM push disabled")
        _firebase_import_failed = True
        return False

    cred = None
    if raw:
        try:
            cred = credentials.Certificate(json.loads(raw))
        except Exception as exc:
            logger.warning("Invalid FIREBASE_SERVICE_ACCOUNT_JSON: %s", exc)
    if cred is None and path and os.path.isfile(path):
        cred = credentials.Certificate(path)
    if cred is None:
        if not _no_firebase_cred_logged:
            logger.info(
                "No Firebase credentials; FCM push disabled "
                "(set GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_SERVICE_ACCOUNT_JSON)"
            )
            _no_firebase_cred_logged = True
        return False
    try:
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(cred)
    except Exception as exc:
        logger.warning("Firebase init failed: %s", exc)
        return False
    _firebase_initialized = True
    return True


def fcm_push_enabled() -> bool:
    return os.getenv("ENABLE_PUSH_NOTIFICATIONS", "1").strip().lower() in {"1", "true", "yes", "on"}


def _user_allows_kind(user: models.PublicUser, kind: str) -> bool:
    if not user.push_enabled:
        return False
    if kind == "reminders":
        return bool(user.push_reminders)
    if kind == "bookings":
        return bool(user.push_bookings)
    if kind == "waitlist":
        return bool(user.push_waitlist)
    if kind == "marketing":
        return bool(user.push_marketing)
    return False


def _collect_tokens(db: Session, public_user_id: int) -> list[str]:
    rows = (
        db.query(models.PublicPushDevice)
        .filter(models.PublicPushDevice.public_user_id == public_user_id)
        .all()
    )
    return [r.fcm_token for r in rows if r.fcm_token]


def _should_drop_token(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    s = str(exc).lower()
    return any(
        part in s
        for part in (
            "not registered",
            "not-found",
            "registration-token-not-registered",
            "invalid-registration",
        )
    )


def send_push_to_public_user(
    db: Session,
    public_user_id: int,
    title: str,
    body: str,
    *,
    kind: str,
    data: dict[str, Any] | None = None,
) -> bool:
    if not fcm_push_enabled():
        return False
    user = db.get(models.PublicUser, public_user_id)
    if not user or user.is_deleted or not _user_allows_kind(user, kind):
        return False
    tokens = _collect_tokens(db, public_user_id)
    if not tokens:
        return False
    if not _init_firebase():
        return False
    try:
        from firebase_admin import messaging
    except ImportError:
        return False

    if not (title or "").strip():
        title = os.getenv("APP_NAME", "Maestro Yoga")
    payload_data = {k: str(v) for k, v in (data or {}).items()}

    try:
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title[:200], body=(body or "")[:2000]),
            data=payload_data,
        )
        response = messaging.send_each_for_multicast(message)
    except Exception as exc:
        logger.exception("FCM multicast failed: %s", exc)
        return False

    invalid: list[str] = []
    for idx, resp in enumerate(response.responses):
        if resp.success:
            continue
        if idx >= len(tokens):
            continue
        if _should_drop_token(resp.exception):
            invalid.append(tokens[idx])
        elif resp.exception:
            logger.warning("FCM token failure: %s", resp.exception)

    if invalid:
        try:
            db.query(models.PublicPushDevice).filter(models.PublicPushDevice.fcm_token.in_(invalid)).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            logger.exception("removing invalid FCM tokens")
            db.rollback()

    return any(resp.success for resp in response.responses)


def public_user_id_for_client_email(db: Session, email: str) -> int | None:
    e = (email or "").strip().lower()
    if not e:
        return None
    u = db.query(models.PublicUser).filter(models.PublicUser.email == e).first()
    return u.id if u else None


def notify_booking_reminder_push(
    db: Session,
    booking_id: int,
    session_title: str,
    center_name: str,
    starts_display: str,
) -> bool:
    booking = db.get(models.Booking, booking_id)
    if not booking:
        return False
    client = db.get(models.Client, booking.client_id)
    if not client:
        return False
    puid = public_user_id_for_client_email(db, client.email)
    if not puid:
        return False
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    title = f"{app_name} — تذكير"
    body = f"جلسة «{session_title}» في {center_name} — {starts_display}"
    return send_push_to_public_user(
        db,
        puid,
        title,
        body,
        kind="reminders",
        data={"type": "session_reminder", "booking_id": str(booking_id)},
    )


def notify_waitlist_slot_push(
    db: Session,
    public_user_id: int,
    session_title: str,
    center_id: int,
    session_id: int,
) -> bool:
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    title = f"{app_name} — مكان متاح"
    body = f"يوجد مكان في جلسة «{session_title}». سارع بالحجز."
    return send_push_to_public_user(
        db,
        public_user_id,
        title,
        body,
        kind="waitlist",
        data={
            "type": "waitlist_open",
            "center_id": str(center_id),
            "session_id": str(session_id),
        },
    )


def safe_notify_booking_confirmed_push(db: Session, booking_id: int) -> None:
    """لا يرفع استثناء — للاستدعاء من مسارات الويب بعد commit."""
    try:
        notify_booking_confirmed_push(db, booking_id)
    except Exception:
        logger.exception("notify_booking_confirmed_push failed booking_id=%s", booking_id)


def notify_booking_confirmed_push(db: Session, booking_id: int) -> bool:
    booking = db.get(models.Booking, booking_id)
    if not booking or booking.status != "confirmed":
        return False
    session = db.get(models.YogaSession, booking.session_id)
    if not session:
        return False
    client = db.get(models.Client, booking.client_id)
    if not client:
        return False
    puid = public_user_id_for_client_email(db, client.email)
    if not puid:
        return False
    center = db.get(models.Center, session.center_id)
    cname = center.name if center else ""
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    title = f"{app_name} — تم تأكيد الحجز"
    body = f"حجزك مؤكّد: «{session.title}»"
    if cname:
        body = f"{body} — {cname}"
    return send_push_to_public_user(
        db,
        puid,
        title,
        body,
        kind="bookings",
        data={
            "type": "booking_confirmed",
            "booking_id": str(booking_id),
            "session_id": str(session.id),
            "center_id": str(session.center_id),
        },
    )


def register_or_refresh_device(
    db: Session,
    public_user_id: int,
    fcm_token: str,
    platform: str,
) -> models.PublicPushDevice:
    raw = (fcm_token or "").strip()
    if not raw or len(raw) > 512:
        raise ValueError("invalid fcm_token")
    plat = (platform or "android").strip().lower()
    if plat not in {"android", "ios"}:
        raise ValueError("platform must be android or ios")
    now = utcnow_naive()
    row = db.query(models.PublicPushDevice).filter(models.PublicPushDevice.fcm_token == raw).first()
    if row:
        row.public_user_id = public_user_id
        row.platform = plat
        row.last_seen_at = now
    else:
        row = models.PublicPushDevice(
            public_user_id=public_user_id,
            fcm_token=raw,
            platform=plat,
            created_at=now,
            last_seen_at=now,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def unregister_device(db: Session, public_user_id: int, fcm_token: str) -> int:
    raw = (fcm_token or "").strip()
    if not raw:
        return 0
    n = (
        db.query(models.PublicPushDevice)
        .filter(
            models.PublicPushDevice.public_user_id == public_user_id,
            models.PublicPushDevice.fcm_token == raw,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return n

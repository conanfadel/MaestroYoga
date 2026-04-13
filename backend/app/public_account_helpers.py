from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .security import create_public_account_delete_token
from .time_utils import utcnow_naive
from .web_shared import (
    PUBLIC_INDEX_DEFAULT_PATH,
    _public_base,
    _sanitize_next_url,
    _url_with_params,
    public_center_id_str_from_next,
    _fmt_dt_weekday_ar,
)

def public_account_phone_prefill(user: models.PublicUser) -> tuple[str, str]:
    """(country_code, local_digits) for account form; default +966 if unknown."""
    raw = (user.phone or "").strip()
    if not raw:
        return "+966", ""
    for prefix in ("+966", "+971", "+965", "+973", "+974", "+968", "+20"):
        if raw.startswith(prefix):
            return prefix, raw[len(prefix) :].lstrip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return "+966", digits


def build_account_delete_confirm_url(
    request: Request, user: models.PublicUser, next_url: str = PUBLIC_INDEX_DEFAULT_PATH
) -> str:
    token = create_public_account_delete_token(user.id, user.email)
    safe_next = _sanitize_next_url(next_url)
    query = urlencode({"token": token, "next": safe_next})
    return f"{_public_base(request)}/public/account/delete/confirm?{query}"


def parse_public_account_center_id(raw: str | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        v = int(s)
    except ValueError:
        return None
    return v if v > 0 else None


def resolve_public_account_center_id(
    *,
    query_center_id: str | None,
    next_url: str,
    db: Session,
    fallback_if_missing_center: bool = True,
) -> int:
    """مركز الولاء/الخطة/الجدول: ?center_id= أو من next، مع التحقق من وجود المركز."""
    cid = parse_public_account_center_id(query_center_id)
    if cid is None:
        try:
            cid = int(public_center_id_str_from_next(next_url))
        except ValueError:
            cid = 1
    if fallback_if_missing_center and db.get(models.Center, cid) is None:
        return 1
    return cid


def public_account_redirect_url(*, msg: str, next_url: str, center_id: int | None) -> str:
    params: dict[str, str] = {"msg": msg, "next": next_url}
    if center_id is not None and center_id > 0:
        params["center_id"] = str(center_id)
    return _url_with_params("/public/account", **params)


def build_public_trainee_schedule_rows(
    db: Session,
    *,
    center_id: int,
    client_id: int,
    upcoming_only: bool = True,
    limit: int = 100,
) -> list[dict[str, str | int]]:
    """جلسات قادمة بحجز مؤكّد مع دفع مسجّل كـ «مدفوع» (يشمل الخطة والدفع لكل جلسة)."""
    now = utcnow_naive()
    paid_exists = (
        db.query(models.Payment.id)
        .filter(
            models.Payment.booking_id == models.Booking.id,
            models.Payment.status == "paid",
        )
        .exists()
    )
    q = (
        db.query(models.Booking, models.YogaSession, models.Room)
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .outerjoin(models.Room, models.Room.id == models.YogaSession.room_id)
        .filter(
            models.Booking.client_id == client_id,
            models.Booking.center_id == center_id,
            models.Booking.status == "confirmed",
            paid_exists,
        )
    )
    if upcoming_only:
        q = q.filter(models.YogaSession.starts_at >= now)
    rows = q.order_by(models.YogaSession.starts_at.asc()).limit(limit).all()
    out: list[dict[str, str | int]] = []
    for _booking, ys, room in rows:
        out.append(
            {
                "session_id": ys.id,
                "title": ys.title or "-",
                "trainer": ys.trainer_name or "-",
                "starts_at_display": _fmt_dt_weekday_ar(ys.starts_at),
                "room_name": room.name if room else "-",
            }
        )
    return out


def build_public_training_assignment_rows(
    db: Session,
    *,
    center_id: int,
    client_id: int,
    active_only: bool = True,
    limit: int = 200,
) -> list[dict[str, str | int]]:
    """تمارين المتدرب المرسلة من الإدارة، مرتبة حسب آخر خطة ثم ترتيب التمرين داخلها."""
    now = utcnow_naive()
    q = (
        db.query(
            models.TrainingAssignmentItem,
            models.TrainingAssignmentBatch,
        )
        .join(
            models.TrainingAssignmentBatch,
            models.TrainingAssignmentBatch.id == models.TrainingAssignmentItem.batch_id,
        )
        .filter(
            models.TrainingAssignmentItem.center_id == center_id,
            models.TrainingAssignmentItem.client_id == client_id,
            models.TrainingAssignmentBatch.center_id == center_id,
            models.TrainingAssignmentBatch.client_id == client_id,
        )
    )
    if active_only:
        q = q.filter(
            models.TrainingAssignmentBatch.status == "active",
            ((models.TrainingAssignmentBatch.starts_at.is_(None)) | (models.TrainingAssignmentBatch.starts_at <= now)),
            ((models.TrainingAssignmentBatch.ends_at.is_(None)) | (models.TrainingAssignmentBatch.ends_at >= now)),
        )
    rows = (
        q.order_by(
            models.TrainingAssignmentBatch.created_at.desc(),
            models.TrainingAssignmentItem.sort_order.asc(),
            models.TrainingAssignmentItem.id.asc(),
        )
        .limit(limit)
        .all()
    )
    out: list[dict[str, str | int]] = []
    for item, batch in rows:
        out.append(
            {
                "batch_id": batch.id,
                "batch_title": (batch.title or "خطة تدريب")[:180],
                "exercise_name": item.exercise_name or "-",
                "muscle_key": item.muscle_key or "-",
                "sets_count": item.sets_count or 0,
                "reps_text": (item.reps_text or "").strip(),
                "duration_minutes": item.duration_minutes or 0,
                "rest_seconds": item.rest_seconds or 0,
                "intensity_text": (item.intensity_text or "").strip(),
                "notes": (item.notes or "").strip(),
            }
        )
    return out

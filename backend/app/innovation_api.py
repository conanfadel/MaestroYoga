"""ميزات إضافية: قائمة انتظار، تقييمات، تقارير، SSE، تقويم ICS، إحالات، رؤى."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .booking_utils import ACTIVE_BOOKING_STATUSES, count_active_bookings, spots_available
from .database import SessionLocal, get_db
from .security import get_public_user_from_token_string, require_roles
from .tenant_utils import require_user_center_id
from .time_utils import utcnow_naive
from .waitlist_service import notify_waitlist_slot_available

logger = logging.getLogger(__name__)

features_router = APIRouter(tags=["features"])
bearer_optional = HTTPBearer(auto_error=False)


def _public_user_dep(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_optional),
    db: Session = Depends(get_db),
) -> models.PublicUser:
    token = (creds.credentials if creds else None) or request.cookies.get("public_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return get_public_user_from_token_string(token, db)


class WaitlistJoinIn(BaseModel):
    session_id: int = Field(..., ge=1)


class RatingIn(BaseModel):
    stars: int = Field(..., ge=1, le=5)
    comment: str | None = None


class FeatureFlagPatch(BaseModel):
    enabled: bool


@features_router.post("/waitlist/join")
def waitlist_join(
    payload: WaitlistJoinIn,
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    session = db.get(models.YogaSession, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.starts_at <= utcnow_naive():
        raise HTTPException(status_code=400, detail="Session already started")
    room = db.get(models.Room, session.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if count_active_bookings(db, session.id) < room.capacity:
        raise HTTPException(status_code=400, detail="Session is not full")
    dup = (
        db.query(models.SessionWaitlist)
        .filter(
            models.SessionWaitlist.session_id == session.id,
            models.SessionWaitlist.public_user_id == user.id,
        )
        .first()
    )
    if dup:
        return {"status": "already_queued", "waitlist_id": dup.id}
    row = models.SessionWaitlist(
        center_id=session.center_id,
        session_id=session.id,
        public_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "queued", "waitlist_id": row.id}


@features_router.delete("/waitlist/{session_id}")
def waitlist_leave(
    session_id: int,
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    row = (
        db.query(models.SessionWaitlist)
        .filter(
            models.SessionWaitlist.session_id == session_id,
            models.SessionWaitlist.public_user_id == user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Not on waitlist")
    db.delete(row)
    db.commit()
    return {"status": "left"}


@features_router.post("/bookings/{booking_id}/rating")
def post_rating(
    booking_id: int,
    payload: RatingIn,
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
):
    booking = db.get(models.Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    client = db.get(models.Client, booking.client_id)
    if not client or client.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your booking")
    session = db.get(models.YogaSession, booking.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session missing")
    if session.starts_at > utcnow_naive():
        raise HTTPException(status_code=400, detail="Session not finished yet")
    existing = db.query(models.SessionRating).filter(models.SessionRating.booking_id == booking_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already rated")
    rating = models.SessionRating(
        booking_id=booking_id,
        stars=payload.stars,
        comment=(payload.comment or "").strip()[:2000] or None,
    )
    db.add(rating)
    db.commit()
    return {"status": "ok", "rating_id": rating.id}


@features_router.post("/bookings/{booking_id}/cancel")
def staff_cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    booking = db.get(models.Booking, booking_id)
    if not booking or booking.center_id != cid:
        raise HTTPException(status_code=404, detail="Booking not found")
    sid = booking.session_id
    booking.status = "cancelled"
    db.commit()
    notify_waitlist_slot_available(db, sid)
    return {"status": "cancelled"}


@features_router.get("/reports/operations")
def operations_report(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
    days: int = Query(30, ge=1, le=366),
):
    cid = require_user_center_id(user)
    since = utcnow_naive() - timedelta(days=days)
    sessions_n = (
        db.query(func.count(models.YogaSession.id))
        .filter(models.YogaSession.center_id == cid, models.YogaSession.starts_at >= since)
        .scalar()
        or 0
    )
    bookings_n = (
        db.query(func.count(models.Booking.id))
        .filter(models.Booking.center_id == cid, models.Booking.booked_at >= since)
        .scalar()
        or 0
    )
    confirmed = (
        db.query(func.count(models.Booking.id))
        .filter(
            models.Booking.center_id == cid,
            models.Booking.booked_at >= since,
            models.Booking.status == "confirmed",
        )
        .scalar()
        or 0
    )
    revenue = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .filter(
            models.Payment.center_id == cid,
            models.Payment.status == "paid",
            models.Payment.paid_at >= since,
        )
        .scalar()
        or 0.0
    )
    pending_pay = (
        db.query(func.count(models.Payment.id))
        .filter(models.Payment.center_id == cid, models.Payment.status == "pending")
        .scalar()
        or 0
    )
    return {
        "center_id": cid,
        "period_days": days,
        "sessions_count": int(sessions_n),
        "bookings_count": int(bookings_n),
        "confirmed_bookings": int(confirmed),
        "revenue_paid": float(revenue),
        "pending_payments": int(pending_pay),
    }


@features_router.get("/insights/demand")
def demand_insights(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
    days: int = Query(90, ge=7, le=365),
):
    cid = require_user_center_id(user)
    since = utcnow_naive() - timedelta(days=days)
    rows = (
        db.query(models.YogaSession.starts_at)
        .filter(models.YogaSession.center_id == cid, models.YogaSession.starts_at >= since)
        .all()
    )
    hours = Counter()
    for (dt,) in rows:
        if dt:
            hours[dt.hour] += 1
    return {
        "center_id": cid,
        "period_days": days,
        "sessions_by_hour": {str(h): hours[h] for h in sorted(hours.keys())},
    }


@features_router.get("/metrics/summary")
def metrics_summary(db: Session = Depends(get_db)):
    """مقاييس خفيفة للمراقبة (للاستخدام مع لوحات أو فحوصات)."""
    return {
        "centers": db.query(func.count(models.Center.id)).scalar() or 0,
        "bookings_total": db.query(func.count(models.Booking.id)).scalar() or 0,
        "public_users": db.query(func.count(models.PublicUser.id)).scalar() or 0,
    }


@features_router.get("/feature-flags")
def list_feature_flags(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    rows = (
        db.query(models.FeatureFlag)
        .filter(
            (models.FeatureFlag.center_id == cid) | (models.FeatureFlag.center_id.is_(None)),
        )
        .all()
    )
    return [
        {"id": r.id, "center_id": r.center_id, "flag_key": r.flag_key, "enabled": r.enabled}
        for r in rows
    ]


@features_router.patch("/feature-flags/{flag_id}")
def patch_feature_flag(
    flag_id: int,
    payload: FeatureFlagPatch,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    row = db.get(models.FeatureFlag, flag_id)
    if not row or (row.center_id is not None and row.center_id != cid):
        raise HTTPException(status_code=404, detail="Flag not found")
    row.enabled = payload.enabled
    db.commit()
    return {"status": "ok"}


@features_router.post("/clients/{client_id}/referral-code")
def ensure_referral_code(
    client_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    cid = require_user_center_id(user)
    client = db.get(models.Client, client_id)
    if not client or client.center_id != cid:
        raise HTTPException(status_code=404, detail="Client not found")
    if client.referral_code:
        return {"referral_code": client.referral_code}
    for _ in range(8):
        code = secrets.token_hex(4).upper()
        clash = (
            db.query(models.Client)
            .filter(models.Client.center_id == cid, models.Client.referral_code == code)
            .first()
        )
        if not clash:
            client.referral_code = code
            db.commit()
            return {"referral_code": code}
    raise HTTPException(status_code=500, detail="Could not allocate code")


@features_router.get("/calendar/centers/{center_id}/sessions.ics")
def center_calendar_ics(center_id: int, db: Session = Depends(get_db)):
    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    now = utcnow_naive()
    sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == center_id, models.YogaSession.starts_at >= now - timedelta(days=1))
        .order_by(models.YogaSession.starts_at.asc())
        .limit(200)
        .all()
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Maestro Yoga//Sessions//AR",
        "CALSCALE:GREGORIAN",
    ]
    for s in sessions:
        uid = f"session-{s.id}@maestro-yoga"
        dtstamp = utcnow_naive().strftime("%Y%m%dT%H%M%SZ")
        start = s.starts_at.strftime("%Y%m%dT%H%M%S")
        end = (s.starts_at + timedelta(minutes=s.duration_minutes)).strftime("%Y%m%dT%H%M%S")
        title = (s.title or "Session").replace("\\", "\\\\").replace(",", "\\,")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{start}",
                f"DTEND:{end}",
                f"SUMMARY:{title}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines) + "\r\n"
    return PlainTextResponse(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="center_{center_id}_sessions.ics"'},
    )


@features_router.get("/stream/sessions")
async def stream_sessions_events(center_id: int = Query(..., ge=1)):
    """SSE: تحديثات خفيفة لعدد الجلسات القادمة (للاستهلاك من الواجهة)."""

    async def gen():
        while True:
            db = SessionLocal()
            try:
                now = utcnow_naive()
                n = (
                    db.query(func.count(models.YogaSession.id))
                    .filter(
                        models.YogaSession.center_id == center_id,
                        models.YogaSession.starts_at >= now,
                    )
                    .scalar()
                    or 0
                )
                payload = json.dumps({"center_id": center_id, "upcoming_sessions": int(n)})
                yield f"data: {payload}\n\n"
            finally:
                db.close()
            await asyncio.sleep(5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@features_router.get("/recommendations/sessions")
def recommend_sessions(
    db: Session = Depends(get_db),
    user: models.PublicUser = Depends(_public_user_dep),
    center_id: int = Query(1, ge=1),
    limit: int = Query(5, ge=1, le=20),
):
    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == user.email.lower())
        .first()
    )
    levels: set[str] = set()
    if client:
        past = (
            db.query(models.YogaSession.level)
            .join(models.Booking, models.Booking.session_id == models.YogaSession.id)
            .filter(
                models.Booking.client_id == client.id,
                models.YogaSession.starts_at < utcnow_naive(),
            )
            .limit(50)
            .all()
        )
        levels = {str(x[0]) for x in past if x[0]}

    q = db.query(models.YogaSession).filter(
        models.YogaSession.center_id == center_id,
        models.YogaSession.starts_at >= utcnow_naive(),
    )
    if levels:
        q = q.filter(models.YogaSession.level.in_(levels))
    rows = q.order_by(models.YogaSession.starts_at.asc()).limit(limit).all()
    return {
        "center_id": center_id,
        "based_on_levels": sorted(levels),
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "level": s.level,
                "starts_at": s.starts_at.isoformat() if s.starts_at else None,
                "price_drop_in": s.price_drop_in,
            }
            for s in rows
        ],
    }

"""Admin HTML report: yoga sessions in a date range."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models
from ...admin_report_helpers import (
    can_access_report_kind,
    report_period_to_range,
    report_previous_period_range,
)
from ...booking_utils import ACTIVE_BOOKING_STATUSES
from ...database import get_db
from ...rbac import user_has_permission
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_sessions_routes(router: APIRouter) -> None:
    from .. import impl_state as core

    @router.get("/admin/reports/sessions", response_class=HTMLResponse)
    def admin_report_sessions(
        request: Request,
        period: str = "today",
        date_from: str = "",
        date_to: str = "",
        db: Session = Depends(get_db),
    ):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if (user.role or "") == "trainer":
            return RedirectResponse(
                url=_url_with_params("/admin/dashboard", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="sessions", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin/dashboard", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
                status_code=303,
            )
        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        d0, d1, range_label, range_err = report_period_to_range(
            period=period,
            date_from_s=date_from,
            date_to_s=date_to,
            parse_optional_date_fn=core._parse_optional_date_str,
            utcnow_fn=utcnow_naive,
        )
        rooms_by_id = {r.id: r for r in db.query(models.Room).filter(models.Room.center_id == cid).all()}
        sessions = (
            db.query(models.YogaSession)
            .filter(
                models.YogaSession.center_id == cid,
                func.date(models.YogaSession.starts_at) >= d0,
                func.date(models.YogaSession.starts_at) <= d1,
            )
            .order_by(models.YogaSession.starts_at.asc())
            .all()
        )
        session_ids = [s.id for s in sessions]
        spots_by_session = core._spots_available_map(db, cid, [int(sid) for sid in session_ids])
        booking_counts: dict[int, dict[str, int]] = defaultdict(lambda: {"active": 0, "cancelled": 0})
        if session_ids:
            for sid, st, cnt in (
                db.query(models.Booking.session_id, models.Booking.status, func.count(models.Booking.id))
                .filter(models.Booking.session_id.in_(session_ids))
                .group_by(models.Booking.session_id, models.Booking.status)
                .all()
            ):
                if st == "cancelled":
                    booking_counts[sid]["cancelled"] += int(cnt)
                elif st in ACTIVE_BOOKING_STATUSES:
                    booking_counts[sid]["active"] += int(cnt)
        level_labels = {
            "beginner": "مبتدئ",
            "intermediate": "متوسط",
            "advanced": "متقدم",
        }
        now_sess = utcnow_naive()
        session_rows: list[dict[str, Any]] = []
        for s in sessions:
            room = rooms_by_id.get(s.room_id)
            bc = booking_counts.get(s.id, {"active": 0, "cancelled": 0})
            cap = room.capacity if room else 0
            spots = spots_by_session.get(int(s.id), 0)
            util_pct = round(100.0 * bc["active"] / cap, 1) if cap > 0 else None
            session_rows.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "trainer_name": s.trainer_name,
                    "level_label": level_labels.get(s.level, s.level),
                    "starts_at_display": _fmt_dt(s.starts_at),
                    "duration_minutes": s.duration_minutes,
                    "room_name": room.name if room else "—",
                    "capacity": cap,
                    "bookings_active": bc["active"],
                    "bookings_cancelled": bc["cancelled"],
                    "spots_free": spots,
                    "utilization_pct": util_pct,
                    "price_drop_in": s.price_drop_in,
                    "is_past": bool(s.starts_at and s.starts_at < now_sess),
                }
            )
        curr_session_count = len(sessions)
        curr_active_bookings = sum(booking_counts[sid]["active"] for sid in session_ids)
        pp0, pp1, prev_sess_label = report_previous_period_range(d0, d1)
        prev_sess_filters = [
            models.YogaSession.center_id == cid,
            func.date(models.YogaSession.starts_at) >= pp0,
            func.date(models.YogaSession.starts_at) <= pp1,
        ]
        prev_session_count = int(
            db.query(func.count(models.YogaSession.id)).filter(*prev_sess_filters).scalar() or 0
        )
        prev_active_bookings = int(
            db.query(func.count(models.Booking.id))
            .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
            .filter(
                models.YogaSession.center_id == cid,
                func.date(models.YogaSession.starts_at) >= pp0,
                func.date(models.YogaSession.starts_at) <= pp1,
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .scalar()
            or 0
        )

        return core.templates.TemplateResponse(
            request,
            "admin_report_sessions.html",
            {
                "center": center,
                "range_label": range_label or "الفترة",
                "range_error": range_err,
                "period": (period or "today").strip().lower(),
                "date_from_val": (date_from or "")[:10],
                "date_to_val": (date_to or "")[:10],
                "session_rows": session_rows,
                "curr_session_count": curr_session_count,
                "curr_active_bookings": curr_active_bookings,
                "prev_sess_label": prev_sess_label,
                "prev_session_count": prev_session_count,
                "prev_active_bookings": prev_active_bookings,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )

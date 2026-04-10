"""Query and chart payload for the admin operational insights report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from ... import models
from ...admin_report_helpers import report_previous_period_range
from ...booking_utils import ACTIVE_BOOKING_STATUSES
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt


def build_insights_template_context(
    *,
    db: Session,
    cid: int,
    center: models.Center | None,
    d0: date,
    d1: date,
    period: str,
    range_label: str | None,
    range_err: str | None,
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    sess_filters = [
        models.YogaSession.center_id == cid,
        func.date(models.YogaSession.starts_at) >= d0,
        func.date(models.YogaSession.starts_at) <= d1,
    ]
    rooms_by_id = {r.id: r for r in db.query(models.Room).filter(models.Room.center_id == cid).all()}

    total_sessions = int(
        db.query(func.count(models.YogaSession.id)).filter(*sess_filters).scalar() or 0
    )
    total_active_bookings = int(
        db.query(func.count(models.Booking.id))
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .filter(*sess_filters, models.Booking.status.in_(ACTIVE_BOOKING_STATUSES))
        .scalar()
        or 0
    )
    total_bookings_all = int(
        db.query(func.count(models.Booking.id))
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .filter(*sess_filters)
        .scalar()
        or 0
    )
    cancelled_bookings = int(
        db.query(func.count(models.Booking.id))
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .filter(*sess_filters, models.Booking.status == "cancelled")
        .scalar()
        or 0
    )
    cancel_rate = round(100.0 * cancelled_bookings / total_bookings_all, 1) if total_bookings_all else 0.0

    top_sessions_raw = (
        db.query(
            models.YogaSession.id,
            models.YogaSession.title,
            models.YogaSession.trainer_name,
            models.YogaSession.starts_at,
            models.YogaSession.room_id,
            func.count(models.Booking.id).label("bk"),
        )
        .outerjoin(
            models.Booking,
            and_(
                models.Booking.session_id == models.YogaSession.id,
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            ),
        )
        .filter(*sess_filters)
        .group_by(
            models.YogaSession.id,
            models.YogaSession.title,
            models.YogaSession.trainer_name,
            models.YogaSession.starts_at,
            models.YogaSession.room_id,
        )
        .order_by(desc(func.count(models.Booking.id)))
        .limit(15)
        .all()
    )
    top_session_rows: list[dict[str, Any]] = []
    for row in top_sessions_raw:
        rid, title, tr, starts, room_id, bk = row
        rm = rooms_by_id.get(room_id)
        top_session_rows.append(
            {
                "id": rid,
                "title": title,
                "trainer_name": tr,
                "starts_at_display": _fmt_dt(starts),
                "room_name": rm.name if rm else "—",
                "bookings": int(bk or 0),
            }
        )

    tr_sess = {
        name: int(n or 0)
        for name, n in db.query(models.YogaSession.trainer_name, func.count(models.YogaSession.id))
        .filter(*sess_filters)
        .group_by(models.YogaSession.trainer_name)
        .all()
    }
    tr_book = {
        name: int(n or 0)
        for name, n in (
            db.query(models.YogaSession.trainer_name, func.count(models.Booking.id))
            .join(
                models.Booking,
                and_(
                    models.Booking.session_id == models.YogaSession.id,
                    models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                ),
            )
            .filter(*sess_filters)
            .group_by(models.YogaSession.trainer_name)
            .all()
        )
    }
    trainer_names = set(tr_sess.keys()) | set(tr_book.keys())
    trainer_merged: list[dict[str, Any]] = []
    for name in trainer_names:
        sn = tr_sess.get(name, 0)
        bn = tr_book.get(name, 0)
        trainer_merged.append(
            {
                "name": name or "—",
                "sessions": sn,
                "bookings": bn,
            }
        )
    trainer_merged.sort(key=lambda x: (x["bookings"], x["sessions"]), reverse=True)

    room_rows_raw = (
        db.query(models.Room.name, func.count(models.YogaSession.id))
        .join(models.YogaSession, models.YogaSession.room_id == models.Room.id)
        .filter(*sess_filters)
        .group_by(models.Room.id, models.Room.name)
        .order_by(func.count(models.YogaSession.id).desc())
        .all()
    )
    room_rows = [{"name": rn or "—", "count": int(c or 0)} for rn, c in room_rows_raw]

    wd_counts = [0] * 7
    hr_counts = [0] * 24
    for (starts_at,) in db.query(models.YogaSession.starts_at).filter(*sess_filters).all():
        if starts_at is None:
            continue
        dow = (starts_at.weekday() + 1) % 7
        wd_counts[dow] += 1
        hr_counts[starts_at.hour] += 1
    weekday_ar = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
    weekday_labels = list(weekday_ar)
    weekday_data = wd_counts
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    hour_data = hr_counts

    avg_bookings_per_session = (
        round(total_active_bookings / total_sessions, 2) if total_sessions else 0.0
    )

    now = utcnow_naive()
    sessions_for_util = (
        db.query(models.YogaSession)
        .filter(*sess_filters)
        .all()
    )
    sid_list = [x.id for x in sessions_for_util]
    bk_active_by_sid: dict[int, int] = {}
    if sid_list:
        for sid, cnt in (
            db.query(models.Booking.session_id, func.count(models.Booking.id))
            .filter(
                models.Booking.session_id.in_(sid_list),
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .group_by(models.Booking.session_id)
            .all()
        ):
            bk_active_by_sid[sid] = int(cnt or 0)
    util_pcts: list[float] = []
    room_util: dict[str, list[float]] = defaultdict(list)
    for s in sessions_for_util:
        rm_u = rooms_by_id.get(s.room_id)
        cap = rm_u.capacity if rm_u else 0
        bct = bk_active_by_sid.get(s.id, 0)
        if cap > 0:
            u = 100.0 * bct / cap
            util_pcts.append(u)
            rn = rm_u.name if rm_u else "—"
            room_util[rn].append(u)
    avg_utilization_pct = round(sum(util_pcts) / len(util_pcts), 1) if util_pcts else 0.0
    room_util_rows = [
        {
            "name": name,
            "avg_util_pct": round(sum(vals) / len(vals), 1) if vals else 0.0,
            "sessions_n": len(vals),
        }
        for name, vals in sorted(room_util.items(), key=lambda x: -len(x[1]))
    ]

    past_sess_ids = [s.id for s in sessions_for_util if s.starts_at < now]
    attend_counts = {"attended": 0, "no_show": 0, "unknown": 0}
    if past_sess_ids:
        for cin, cnt in (
            db.query(models.Booking.checked_in, func.count(models.Booking.id))
            .filter(
                models.Booking.session_id.in_(past_sess_ids),
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .group_by(models.Booking.checked_in)
            .all()
        ):
            cni = int(cnt or 0)
            if cin is True:
                attend_counts["attended"] += cni
            elif cin is False:
                attend_counts["no_show"] += cni
            else:
                attend_counts["unknown"] += cni

    ip0, ip1, prev_insights_label = report_previous_period_range(d0, d1)
    prev_sess_filters_ins = [
        models.YogaSession.center_id == cid,
        func.date(models.YogaSession.starts_at) >= ip0,
        func.date(models.YogaSession.starts_at) <= ip1,
    ]
    prev_total_sessions = int(
        db.query(func.count(models.YogaSession.id)).filter(*prev_sess_filters_ins).scalar() or 0
    )
    prev_total_active_bookings = int(
        db.query(func.count(models.Booking.id))
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .filter(*prev_sess_filters_ins, models.Booking.status.in_(ACTIVE_BOOKING_STATUSES))
        .scalar()
        or 0
    )
    bookings_goal_pct: float | None = None
    mb_goal = int(center.monthly_bookings_goal) if center and center.monthly_bookings_goal is not None else None
    if mb_goal and mb_goal > 0 and (period or "").strip().lower() == "month":
        bookings_goal_pct = round(100.0 * total_active_bookings / mb_goal, 1)

    charts_payload = {
        "trainers": {
            "labels": [t["name"][:28] for t in trainer_merged[:12]],
            "data": [t["bookings"] for t in trainer_merged[:12]],
        },
        "sessions": {
            "labels": [((t["title"] or "")[:22] + f" #{t['id']}") for t in top_session_rows[:10]],
            "data": [t["bookings"] for t in top_session_rows[:10]],
        },
        "weekday": {"labels": weekday_labels, "data": weekday_data},
        "hour": {"labels": hour_labels, "data": hour_data},
        "rooms": {
            "labels": [r["name"][:24] for r in room_rows[:10]],
            "data": [r["count"] for r in room_rows[:10]],
        },
    }
    charts_json = json.dumps(charts_payload, ensure_ascii=False)

    return {
        "center": center,
        "range_label": range_label or "الفترة",
        "range_error": range_err,
        "period": (period or "month").strip().lower(),
        "date_from_val": (date_from or "")[:10],
        "date_to_val": (date_to or "")[:10],
        "total_sessions": total_sessions,
        "total_active_bookings": total_active_bookings,
        "cancel_rate": cancel_rate,
        "cancelled_bookings": cancelled_bookings,
        "avg_bookings_per_session": avg_bookings_per_session,
        "top_session_rows": top_session_rows,
        "trainer_rows": trainer_merged[:20],
        "room_rows": room_rows,
        "charts_json": charts_json,
        "avg_utilization_pct": avg_utilization_pct,
        "room_util_rows": room_util_rows,
        "attend_counts": attend_counts,
        "prev_insights_label": prev_insights_label,
        "prev_total_sessions": prev_total_sessions,
        "prev_total_active_bookings": prev_total_active_bookings,
        "bookings_goal_pct": bookings_goal_pct,
        "monthly_bookings_goal": mb_goal,
        "generated_at": _fmt_dt(utcnow_naive()),
    }

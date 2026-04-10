"""7-day revenue bars and today/tomorrow ops rows + schedule overlap detection."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .. import impl_state as _s


def build_revenue_7d_bars(db: _s.Session, cid: int, today: Any) -> list[dict[str, Any]]:
    revenue_7d_bars: list[dict[str, Any]] = []
    max_rev_7d = 0.01
    rev_start = today - _s.timedelta(days=6)
    revenue_7d_rows = (
        db.query(
            _s.func.date(_s.models.Payment.paid_at).label("day"),
            _s.func.coalesce(_s.func.sum(_s.models.Payment.amount), 0.0),
        )
        .filter(
            _s.models.Payment.center_id == cid,
            _s.models.Payment.status == "paid",
            _s.func.date(_s.models.Payment.paid_at) >= rev_start,
            _s.func.date(_s.models.Payment.paid_at) <= today,
        )
        .group_by(_s.func.date(_s.models.Payment.paid_at))
        .all()
    )
    revenue_by_day = {str(day): float(total or 0.0) for day, total in revenue_7d_rows}
    for i in range(6, -1, -1):
        d = today - _s.timedelta(days=i)
        amt = revenue_by_day.get(d.isoformat(), 0.0)
        revenue_7d_bars.append({"date_iso": d.isoformat(), "amount": amt, "label": f"{d.day}/{d.month}"})
        max_rev_7d = max(max_rev_7d, amt)
    for bar in revenue_7d_bars:
        bar["bar_pct"] = int(round(100 * float(bar["amount"]) / max_rev_7d)) if max_rev_7d > 0 else 0
    return revenue_7d_bars


def build_ops_rows_and_schedule_conflicts(
    db: _s.Session,
    cid: int,
    rooms_by_id: dict[int, Any],
    today: Any,
    tomorrow_d: Any,
    now_na: Any,
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]], list[dict[str, str | int]]]:
    ops_sessions_q = (
        db.query(_s.models.YogaSession)
        .filter(
            _s.models.YogaSession.center_id == cid,
            _s.or_(
                _s.func.date(_s.models.YogaSession.starts_at) == today,
                _s.func.date(_s.models.YogaSession.starts_at) == tomorrow_d,
            ),
        )
        .order_by(_s.models.YogaSession.starts_at.asc())
        .limit(36)
        .all()
    )
    ops_spots = _s._spots_available_map(db, cid, [int(s.id) for s in ops_sessions_q])
    ops_today_rows: list[dict[str, str | int]] = []
    ops_tomorrow_rows: list[dict[str, str | int]] = []
    for s in ops_sessions_q:
        room = rooms_by_id.get(s.room_id)
        row = {
            "id": s.id,
            "title": s.title,
            "trainer": s.trainer_name,
            "room": room.name if room else "-",
            "starts": _s._fmt_dt(s.starts_at),
            "spots": ops_spots.get(int(s.id), 0),
            "capacity": room.capacity if room else 0,
        }
        if s.starts_at.date() == today:
            ops_today_rows.append(row)
        elif s.starts_at.date() == tomorrow_d:
            ops_tomorrow_rows.append(row)

    window_start = now_na - _s.timedelta(hours=6)
    future_for_conflicts = (
        db.query(_s.models.YogaSession)
        .filter(_s.models.YogaSession.center_id == cid, _s.models.YogaSession.starts_at >= window_start)
        .order_by(_s.models.YogaSession.room_id, _s.models.YogaSession.starts_at)
        .all()
    )
    by_room_sessions: dict[int, list[_s.models.YogaSession]] = defaultdict(list)
    for s in future_for_conflicts:
        by_room_sessions[s.room_id].append(s)
    schedule_conflicts: list[dict[str, str | int]] = []
    for rid, lst in by_room_sessions.items():
        lst.sort(key=lambda x: x.starts_at)
        for i in range(len(lst) - 1):
            a, b = lst[i], lst[i + 1]
            end_a = a.starts_at + _s.timedelta(minutes=int(a.duration_minutes or 0))
            if end_a > b.starts_at:
                schedule_conflicts.append(
                    {
                        "room_name": (rooms_by_id.get(rid).name if rooms_by_id.get(rid) else f"غرفة #{rid}"),
                        "a_id": a.id,
                        "a_title": a.title,
                        "a_start": _s._fmt_dt(a.starts_at),
                        "b_id": b.id,
                        "b_title": b.title,
                        "b_start": _s._fmt_dt(b.starts_at),
                    }
                )
    return ops_today_rows, ops_tomorrow_rows, schedule_conflicts

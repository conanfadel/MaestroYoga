"""Admin HTML report pages (sessions, revenue, insights, clients, subscriptions, health, security audit, report settings)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, case, desc, func
from sqlalchemy.orm import Session

from .. import models
from ..admin_export_helpers import clients_new_returning_for_range
from ..admin_report_helpers import (
    build_subscription_report_rows,
    can_access_report_kind,
    effective_vat_percent_for_center,
    parse_optional_non_negative_float,
    parse_optional_non_negative_int,
    payment_method_label_ar,
    report_period_to_range,
    report_previous_period_range,
    vat_inclusive_breakdown,
)
from ..booking_utils import ACTIVE_BOOKING_STATUSES
from ..database import get_db
from ..rbac import user_has_permission
from ..security_audit import log_security_event
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_routes(router: APIRouter) -> None:
    from . import impl_state as core

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
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="sessions", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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


    @router.get("/admin/reports/revenue", response_class=HTMLResponse)
    def admin_report_revenue(
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
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="revenue", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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
        vat_pct = effective_vat_percent_for_center(center=center)

        base_pf = [
            models.Payment.center_id == cid,
            func.date(models.Payment.paid_at) >= d0,
            func.date(models.Payment.paid_at) <= d1,
        ]
        paid_total = float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(*base_pf, models.Payment.status == "paid")
            .scalar()
            or 0.0
        )
        vat_breakdown = vat_inclusive_breakdown(paid_total, vat_pct)
        paid_count = (
            db.query(func.count(models.Payment.id)).filter(*base_pf, models.Payment.status == "paid").scalar()
            or 0
        )
        p0, p1, prev_period_label = report_previous_period_range(d0, d1)
        prev_pf = [
            models.Payment.center_id == cid,
            func.date(models.Payment.paid_at) >= p0,
            func.date(models.Payment.paid_at) <= p1,
        ]
        prev_paid_total = float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(*prev_pf, models.Payment.status == "paid")
            .scalar()
            or 0.0
        )
        prev_paid_count = int(
            db.query(func.count(models.Payment.id)).filter(*prev_pf, models.Payment.status == "paid").scalar() or 0
        )
        paid_delta_pct = (
            round(100.0 * (paid_total - prev_paid_total) / prev_paid_total, 1)
            if prev_paid_total > 0
            else None
        )
        count_delta = int(paid_count - prev_paid_count)

        by_day = (
            db.query(
                func.date(models.Payment.paid_at).label("d"),
                func.coalesce(func.sum(models.Payment.amount), 0.0),
            )
            .filter(*base_pf, models.Payment.status == "paid")
            .group_by(func.date(models.Payment.paid_at))
            .order_by(func.date(models.Payment.paid_at).asc())
            .all()
        )
        by_method = (
            db.query(
                models.Payment.payment_method,
                func.count(models.Payment.id),
                func.coalesce(func.sum(models.Payment.amount), 0.0),
            )
            .filter(*base_pf, models.Payment.status == "paid")
            .group_by(models.Payment.payment_method)
            .all()
        )
        by_status = (
            db.query(
                models.Payment.status,
                func.count(models.Payment.id),
                func.coalesce(func.sum(models.Payment.amount), 0.0),
            )
            .filter(*base_pf)
            .group_by(models.Payment.status)
            .all()
        )
        sub_cond = models.Payment.payment_method.like("subscription_%")
        cat_session_count, cat_session_amount, cat_sub_count, cat_sub_amount, cat_other_count, cat_other_amount = (
            db.query(
                func.coalesce(
                    func.sum(case((and_(~sub_cond, models.Payment.booking_id.is_not(None)), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(~sub_cond, models.Payment.booking_id.is_not(None)),
                                models.Payment.amount,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
                func.coalesce(func.sum(case((sub_cond, 1), else_=0)), 0),
                func.coalesce(func.sum(case((sub_cond, models.Payment.amount), else_=0.0)), 0.0),
                func.coalesce(
                    func.sum(case((and_(~sub_cond, models.Payment.booking_id.is_(None)), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(~sub_cond, models.Payment.booking_id.is_(None)),
                                models.Payment.amount,
                            ),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ),
            )
            .filter(*base_pf, models.Payment.status == "paid")
            .one()
        )
        cat_session = {"count": int(cat_session_count or 0), "amount": float(cat_session_amount or 0.0)}
        cat_sub = {"count": int(cat_sub_count or 0), "amount": float(cat_sub_amount or 0.0)}
        cat_other = {"count": int(cat_other_count or 0), "amount": float(cat_other_amount or 0.0)}
        product_rows = [
            {"label": "حجز جلسة (مرتبط بحجز)", **cat_session},
            {"label": "اشتراك / باقة", **cat_sub},
            {"label": "أخرى (بدون ربط حجز)", **cat_other},
        ]

        status_counts: dict[str, tuple[int, float]] = {}
        for st, c, a in by_status:
            status_counts[st] = (int(c), float(a or 0))
        paid_n = status_counts.get("paid", (0, 0.0))[0]
        failed_n = status_counts.get("failed", (0, 0.0))[0]
        pend_n = status_counts.get("pending", (0, 0.0))[0] + status_counts.get("pending_payment", (0, 0.0))[0]
        terminal_n = paid_n + failed_n + pend_n
        success_rate_pct = round(100.0 * paid_n / terminal_n, 1) if terminal_n else 0.0

        now = utcnow_naive()
        anchor = func.coalesce(models.Payment.created_at, models.Payment.paid_at, now)
        cutoff_1d = now - timedelta(days=1)
        cutoff_7d = now - timedelta(days=7)
        (
            pending_open_count,
            pending_total_amt,
            p01_n,
            p01_amt,
            p27_n,
            p27_amt,
            p8p_n,
            p8p_amt,
        ) = (
            db.query(
                func.count(models.Payment.id),
                func.coalesce(func.sum(models.Payment.amount), 0.0),
                func.coalesce(func.sum(case((anchor >= cutoff_1d, 1), else_=0)), 0),
                func.coalesce(func.sum(case((anchor >= cutoff_1d, models.Payment.amount), else_=0.0)), 0.0),
                func.coalesce(func.sum(case((and_(anchor < cutoff_1d, anchor >= cutoff_7d), 1), else_=0)), 0),
                func.coalesce(
                    func.sum(case((and_(anchor < cutoff_1d, anchor >= cutoff_7d), models.Payment.amount), else_=0.0)),
                    0.0,
                ),
                func.coalesce(func.sum(case((anchor < cutoff_7d, 1), else_=0)), 0),
                func.coalesce(func.sum(case((anchor < cutoff_7d, models.Payment.amount), else_=0.0)), 0.0),
            )
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status.in_(("pending", "pending_payment")),
            )
            .one()
        )
        pend_age_buckets = {
            "0_1": {"n": int(p01_n or 0), "amt": float(p01_amt or 0.0)},
            "2_7": {"n": int(p27_n or 0), "amt": float(p27_amt or 0.0)},
            "8p": {"n": int(p8p_n or 0), "amt": float(p8p_amt or 0.0)},
        }
        pending_total_amt = float(pending_total_amt or 0.0)
        pending_open_count = int(pending_open_count or 0)

        refund_count, refund_sum = (
            db.query(
                func.count(models.Payment.id),
                func.coalesce(func.sum(models.Payment.amount), 0.0),
            )
            .filter(*base_pf, models.Payment.status == "refunded")
            .one()
        )
        refund_count = int(refund_count or 0)
        refund_sum = float(refund_sum or 0.0)

        revenue_goal_pct: float | None = None
        monthly_rev_goal = float(center.monthly_revenue_goal) if center and center.monthly_revenue_goal is not None else None
        if monthly_rev_goal and monthly_rev_goal > 0 and (period or "").strip().lower() == "month":
            revenue_goal_pct = round(100.0 * paid_total / monthly_rev_goal, 1)

        day_rows = [{"d": row[0], "amount": float(row[1] or 0)} for row in by_day]
        method_rows = [
            {
                "method": payment_method_label_ar(m),
                "method_id": m or "",
                "count": int(c),
                "amount": float(a or 0),
            }
            for m, c, a in by_method
        ]
        status_labels = {
            "paid": "مدفوع",
            "pending": "معلّق",
            "pending_payment": "بانتظار الدفع",
            "failed": "فاشل",
            "refunded": "مسترد",
        }
        status_rows = [
            {
                "status": status_labels.get(st, st),
                "status_id": st,
                "count": int(c),
                "amount": float(a or 0),
            }
            for st, c, a in by_status
        ]
        revenue_charts_json = json.dumps(
            {
                "daily": {
                    "labels": [str(r["d"]) for r in day_rows],
                    "data": [r["amount"] for r in day_rows],
                },
                "methods": {
                    "labels": [r["method"][:28] for r in method_rows],
                    "data": [r["amount"] for r in method_rows],
                },
            },
            ensure_ascii=False,
        )
        export_q = _url_with_params(
            "/admin/export/payments.csv",
            **{
                core.ADMIN_QP_PAYMENT_DATE_FROM: d0.isoformat(),
                core.ADMIN_QP_PAYMENT_DATE_TO: d1.isoformat(),
            },
        )
        return core.templates.TemplateResponse(
            request,
            "admin_report_revenue.html",
            {
                "center": center,
                "range_label": range_label or "الفترة",
                "range_error": range_err,
                "period": (period or "today").strip().lower(),
                "date_from_val": (date_from or "")[:10],
                "date_to_val": (date_to or "")[:10],
                "paid_total": paid_total,
                "paid_count": int(paid_count),
                "prev_period_label": prev_period_label,
                "prev_paid_total": prev_paid_total,
                "prev_paid_count": prev_paid_count,
                "paid_delta_pct": paid_delta_pct,
                "count_delta": count_delta,
                "vat_rate_percent": vat_pct,
                "vat_net": vat_breakdown["net"],
                "vat_amount": vat_breakdown["vat"],
                "product_rows": product_rows,
                "success_rate_pct": success_rate_pct,
                "pending_total_amt": pending_total_amt,
                "pending_open_count": pending_open_count,
                "pend_age_buckets": pend_age_buckets,
                "day_rows": day_rows,
                "method_rows": method_rows,
                "status_rows": status_rows,
                "revenue_charts_json": revenue_charts_json,
                "export_payments_csv_url": export_q,
                "refund_count": refund_count,
                "refund_sum": refund_sum,
                "revenue_goal_pct": revenue_goal_pct,
                "monthly_revenue_goal": monthly_rev_goal,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )


    @router.get("/admin/reports/insights", response_class=HTMLResponse)
    def admin_report_insights(
        request: Request,
        period: str = "week",
        date_from: str = "",
        date_to: str = "",
        db: Session = Depends(get_db),
    ):
        """رؤى تشغيلية: أكثر الجلسات حجزاً، نشاط المدربين، توزيع الأيام والساعات والغرف، ومخططات."""
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if (user.role or "") == "trainer":
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="insights", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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

        # Count by weekday/hour in Python so SQLite + PostgreSQL both work (strftime is SQLite-only).
        wd_counts = [0] * 7
        hr_counts = [0] * 24
        for (starts_at,) in db.query(models.YogaSession.starts_at).filter(*sess_filters).all():
            if starts_at is None:
                continue
            dow = (starts_at.weekday() + 1) % 7  # Sunday=0 .. Saturday=6 (matches SQLite %w)
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

        return core.templates.TemplateResponse(
            request,
            "admin_report_insights.html",
            {
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
            },
        )


    @router.get("/admin/reports/clients", response_class=HTMLResponse)
    def admin_report_clients(
        request: Request,
        period: str = "month",
        date_from: str = "",
        date_to: str = "",
        db: Session = Depends(get_db),
    ):
        """عملاء جدد مقابل عائدون ضمن حجوزات الجلسات في الفترة."""
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if (user.role or "") == "trainer":
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="clients", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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
        new_clients, returning_clients, distinct_booking_clients = clients_new_returning_for_range(
            db=db,
            models_module=models,
            center_id=cid,
            d0=d0,
            d1=d1,
            active_booking_statuses=ACTIVE_BOOKING_STATUSES,
            func_module=func,
        )
        pp0, pp1, prev_clients_label = report_previous_period_range(d0, d1)
        prev_new, prev_returning, prev_distinct = clients_new_returning_for_range(
            db=db,
            models_module=models,
            center_id=cid,
            d0=pp0,
            d1=pp1,
            active_booking_statuses=ACTIVE_BOOKING_STATUSES,
            func_module=func,
        )

        return core.templates.TemplateResponse(
            request,
            "admin_report_clients.html",
            {
                "center": center,
                "range_label": range_label or "الفترة",
                "range_error": range_err,
                "period": (period or "month").strip().lower(),
                "date_from_val": (date_from or "")[:10],
                "date_to_val": (date_to or "")[:10],
                "new_clients": new_clients,
                "returning_clients": returning_clients,
                "distinct_booking_clients": distinct_booking_clients,
                "prev_clients_label": prev_clients_label,
                "prev_new_clients": prev_new,
                "prev_returning_clients": prev_returning,
                "prev_distinct_booking_clients": prev_distinct,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )


    @router.get("/admin/reports/subscriptions", response_class=HTMLResponse)
    def admin_report_subscriptions(
        request: Request,
        days: int = 30,
        db: Session = Depends(get_db),
    ):
        """اشتراكات تنتهي قريباً مع حد الجلسات في الخطة."""
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if (user.role or "") == "trainer":
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="subscriptions", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
                status_code=303,
            )
        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        if days < 1 or days > 365:
            days = 30
        today = utcnow_naive().date()
        horizon = today + timedelta(days=days)
        rows_raw = (
            db.query(models.ClientSubscription, models.Client, models.SubscriptionPlan)
            .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
            .join(models.SubscriptionPlan, models.SubscriptionPlan.id == models.ClientSubscription.plan_id)
            .filter(
                models.Client.center_id == cid,
                models.ClientSubscription.status == "active",
                func.date(models.ClientSubscription.end_date) >= today,
                func.date(models.ClientSubscription.end_date) <= horizon,
            )
            .order_by(models.ClientSubscription.end_date.asc())
            .all()
        )
        sub_rows = build_subscription_report_rows(rows_raw=rows_raw, fmt_dt_fn=_fmt_dt)

        return core.templates.TemplateResponse(
            request,
            "admin_report_subscriptions.html",
            {
                "center": center,
                "days": days,
                "sub_rows": sub_rows,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )


    @router.get("/admin/reports/health", response_class=HTMLResponse)
    def admin_report_health(request: Request, db: Session = Depends(get_db)):
        """مؤشرات تقنية وتشغيلية خفيفة للمركز."""
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if (user.role or "") == "trainer":
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="health", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
                status_code=303,
            )
        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        today = utcnow_naive().date()
        d7 = today - timedelta(days=7)
        d30 = today - timedelta(days=30)

        def _failed_count(since: date) -> int:
            return int(
                db.query(func.count(models.Payment.id))
                .filter(
                    models.Payment.center_id == cid,
                    models.Payment.status == "failed",
                    func.date(models.Payment.paid_at) >= since,
                    func.date(models.Payment.paid_at) <= today,
                )
                .scalar()
                or 0
            )

        failed_7d = _failed_count(d7)
        failed_30d = _failed_count(d30)
        pending_n = int(
            db.query(func.count(models.Payment.id))
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status.in_(("pending", "pending_payment")),
            )
            .scalar()
            or 0
        )
        blocked_ips = int(
            db.query(func.count(models.BlockedIP.id)).filter(models.BlockedIP.is_active.is_(True)).scalar() or 0
        )

        return core.templates.TemplateResponse(
            request,
            "admin_report_health.html",
            {
                "center": center,
                "failed_7d": failed_7d,
                "failed_30d": failed_30d,
                "pending_payments_open": pending_n,
                "blocked_ips_active": blocked_ips,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )


    @router.get("/admin/reports/security-audit", response_class=HTMLResponse)
    def admin_report_security_audit(
        request: Request,
        period: str = "month",
        date_from: str = "",
        date_to: str = "",
        audit_event_type: str = "",
        audit_status: str = "",
        db: Session = Depends(get_db),
    ):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_has_permission(user, "security.audit"):
            return core._security_owner_forbidden_redirect()
        d0, d1, range_label, range_err = report_period_to_range(
            period=period,
            date_from_s=date_from,
            date_to_s=date_to,
            parse_optional_date_fn=core._parse_optional_date_str,
            utcnow_fn=utcnow_naive,
        )
        q = db.query(models.SecurityAuditEvent).filter(
            func.date(models.SecurityAuditEvent.created_at) >= d0,
            func.date(models.SecurityAuditEvent.created_at) <= d1,
        )
        if audit_event_type.strip():
            q = q.filter(models.SecurityAuditEvent.event_type == audit_event_type.strip())
        if audit_status.strip():
            q = q.filter(models.SecurityAuditEvent.status == audit_status.strip())
        events = q.order_by(models.SecurityAuditEvent.created_at.desc()).limit(400).all()
        csv_url = _url_with_params(
            "/admin/security/export/csv",
            **{
                "audit_date_from": d0.isoformat(),
                "audit_date_to": d1.isoformat(),
                **({"audit_event_type": audit_event_type.strip()} if audit_event_type.strip() else {}),
                **({"audit_status": audit_status.strip()} if audit_status.strip() else {}),
            },
        )
        return core.templates.TemplateResponse(
            request,
            "admin_report_security_audit.html",
            {
                "range_label": range_label or "الفترة",
                "range_error": range_err,
                "period": (period or "month").strip().lower(),
                "date_from_val": (date_from or "")[:10],
                "date_to_val": (date_to or "")[:10],
                "audit_event_type": audit_event_type.strip(),
                "audit_status": audit_status.strip(),
                "events": events,
                "csv_url": csv_url,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )


    @router.post("/admin/center/report-settings")
    def admin_center_report_settings(
        request: Request,
        monthly_revenue_goal: str = Form(""),
        monthly_bookings_goal: str = Form(""),
        vat_rate_percent: str = Form(""),
        report_digest_email: str = Form(""),
        return_section: str = Form("section-reports"),
        db: Session = Depends(get_db),
    ):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_has_permission(user, "center.settings.edit"):
            return core._admin_redirect(core.ADMIN_MSG_REPORT_FORBIDDEN, return_section=return_section)
        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        if not center:
            return core._admin_redirect(core.ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, return_section=return_section)
        center.monthly_revenue_goal = parse_optional_non_negative_float(monthly_revenue_goal)
        center.monthly_bookings_goal = parse_optional_non_negative_int(monthly_bookings_goal)
        s_vat = (vat_rate_percent or "").strip()
        if not s_vat:
            center.vat_rate_percent = None
        else:
            vr = parse_optional_non_negative_float(s_vat)
            center.vat_rate_percent = vr if vr is not None and vr <= 100 else None
        em = (report_digest_email or "").strip()[:220]
        center.report_digest_email = em or None
        db.commit()
        log_security_event(
            "admin_center_report_settings_saved",
            request,
            "success",
            email=user.email,
            details={"center_id": cid},
        )
        return core._admin_redirect("report_settings_saved", return_section=return_section)



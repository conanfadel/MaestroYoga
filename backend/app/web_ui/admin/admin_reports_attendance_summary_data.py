"""Data loading and digest content for attendance / print / email summary routes."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape as html_escape
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models
from ...booking_utils import ACTIVE_BOOKING_STATUSES
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt


def load_session_attendance_template_context(
    db: Session, cid: int, session_id: int
) -> dict[str, Any] | None:
    ys = db.get(models.YogaSession, session_id)
    if not ys or ys.center_id != cid:
        return None
    center = db.get(models.Center, cid)
    rows_raw = (
        db.query(models.Booking, models.Client)
        .join(models.Client, models.Client.id == models.Booking.client_id)
        .filter(models.Booking.session_id == session_id)
        .order_by(models.Booking.id.asc())
        .all()
    )
    booking_rows: list[dict[str, Any]] = []
    for bk, cl in rows_raw:
        booking_rows.append(
            {
                "booking_id": bk.id,
                "client_name": cl.full_name,
                "status": bk.status,
                "checked_in": bk.checked_in,
            }
        )
    return {
        "center": center,
        "session": ys,
        "starts_display": _fmt_dt(ys.starts_at),
        "booking_rows": booking_rows,
    }


def _today_core_metrics(db: Session, cid: int, today: date) -> tuple[float, int, int]:
    paid_revenue_today = float(
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .filter(
            models.Payment.center_id == cid,
            models.Payment.status == "paid",
            func.date(models.Payment.paid_at) == today,
        )
        .scalar()
        or 0.0
    )
    sessions_scheduled_today = int(
        db.query(func.count(models.YogaSession.id))
        .filter(models.YogaSession.center_id == cid, func.date(models.YogaSession.starts_at) == today)
        .scalar()
        or 0
    )
    bookings_active_today = int(
        db.query(func.count(models.Booking.id))
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .filter(
            models.YogaSession.center_id == cid,
            func.date(models.YogaSession.starts_at) == today,
            models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .scalar()
        or 0
    )
    return paid_revenue_today, sessions_scheduled_today, bookings_active_today


def build_print_summary_template_context(db: Session, cid: int) -> dict[str, Any]:
    center = db.get(models.Center, cid)
    today = utcnow_naive().date()
    now_na = utcnow_naive()
    paid_revenue_today, sessions_scheduled_today, bookings_active_today = _today_core_metrics(db, cid, today)
    subs_7 = (
        db.query(models.ClientSubscription)
        .join(models.Client, models.Client.id == models.ClientSubscription.client_id)
        .filter(
            models.Client.center_id == cid,
            models.ClientSubscription.status == "active",
            models.ClientSubscription.end_date >= now_na,
            models.ClientSubscription.end_date <= now_na + timedelta(days=7),
        )
        .count()
    )
    pending_stale = 0
    for pr in (
        db.query(models.Payment)
        .filter(
            models.Payment.center_id == cid,
            models.Payment.status.in_(("pending", "pending_payment")),
        )
        .all()
    ):
        anchor = pr.created_at or pr.paid_at or now_na
        if (now_na - anchor).days >= 8:
            pending_stale += 1
    failed_7d = int(
        db.query(func.count(models.Payment.id))
        .filter(
            models.Payment.center_id == cid,
            models.Payment.status == "failed",
            func.date(models.Payment.paid_at) >= today - timedelta(days=7),
            func.date(models.Payment.paid_at) <= today,
        )
        .scalar()
        or 0
    )
    return {
        "center": center,
        "paid_revenue_today": paid_revenue_today,
        "sessions_scheduled_today": sessions_scheduled_today,
        "bookings_active_today": bookings_active_today,
        "subs_expiring_7d": int(subs_7),
        "pending_stale_8d": pending_stale,
        "failed_7d": failed_7d,
        "generated_at": _fmt_dt(utcnow_naive()),
    }


def fetch_daily_digest_core_metrics(db: Session, cid: int) -> tuple[float, int, int]:
    today = utcnow_naive().date()
    return _today_core_metrics(db, cid, today)


def build_digest_mail_parts(
    center: models.Center | None, today: date, rev: float, st: int, bk: int
) -> tuple[str, str, str]:
    name = center.name if center else ""
    subject = f"ملخص تشغيلي — {name or 'Maestro'} — {today.isoformat()}"
    plain = f"ملخص {name}\nجلسات: {st}\nحجوزات: {bk}\nإيراد: {rev:.2f} SAR\n"
    html = (
        f"<html><body dir='rtl' style='font-family:Tahoma,sans-serif'>"
        f"<h2>ملخص يومي — {html_escape(name)}</h2>"
        f"<p>التاريخ: {today.isoformat()}</p>"
        f"<ul>"
        f"<li>جلسات مجدولة اليوم: {st}</li>"
        f"<li>حجوزات نشطة اليوم: {bk}</li>"
        f"<li>إيراد مدفوع اليوم: {rev:.2f} SAR</li>"
        f"</ul>"
        f"<p><a href='/admin/reports/print-summary'>صفحة ملخص للطباعة</a></p>"
        f"</body></html>"
    )
    return subject, plain, html

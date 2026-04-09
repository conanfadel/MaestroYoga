"""Session attendance, daily print summary, email digest — HTML routes."""

from __future__ import annotations

from datetime import timedelta
from html import escape as html_escape
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..booking_utils import ACTIVE_BOOKING_STATUSES
from ..database import get_db
from ..mailer import send_mail_with_attachments
from ..rbac import user_has_permission
from ..security_audit import log_security_event
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..admin_report_helpers import user_can_report_health
from ..web_shared import _fmt_dt, _url_with_params


def register_admin_report_attendance_summary_routes(router: APIRouter) -> None:
    from . import impl_state as core

    @router.get("/admin/session/{session_id}/attendance", response_class=HTMLResponse)
    def admin_session_attendance(
        session_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_has_permission(user, "sessions.manage"):
            return core._trainer_forbidden_redirect("section-sessions")
        cid = require_user_center_id(user)
        ys = db.get(models.YogaSession, session_id)
        if not ys or ys.center_id != cid:
            raise HTTPException(status_code=404, detail="Session not found")
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
        return core.templates.TemplateResponse(
            request,
            "admin_session_attendance.html",
            {
                "center": center,
                "session": ys,
                "starts_display": _fmt_dt(ys.starts_at),
                "booking_rows": booking_rows,
            },
        )


    @router.post("/admin/booking/attendance")
    def admin_booking_attendance_post(
        request: Request,
        booking_id: int = Form(...),
        mark: str = Form(...),
        db: Session = Depends(get_db),
    ):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_has_permission(user, "sessions.manage"):
            return core._trainer_forbidden_redirect("section-sessions")
        cid = require_user_center_id(user)
        bk = db.get(models.Booking, booking_id)
        if not bk or bk.center_id != cid:
            raise HTTPException(status_code=404, detail="Booking not found")
        m = (mark or "").strip().lower()
        if m == "present":
            bk.checked_in = True
        elif m == "absent":
            bk.checked_in = False
        elif m in {"clear", "unknown"}:
            bk.checked_in = None
        else:
            return RedirectResponse(url=f"/admin/session/{bk.session_id}/attendance", status_code=303)
        db.commit()
        log_security_event(
            "booking_attendance_set",
            request,
            "success",
            email=user.email,
            details={"booking_id": booking_id, "mark": m},
        )
        return RedirectResponse(url=f"/admin/session/{bk.session_id}/attendance", status_code=303)


    @router.get("/admin/reports/print-summary", response_class=HTMLResponse)
    def admin_reports_print_summary(request: Request, db: Session = Depends(get_db)):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_can_report_health(user=user, user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
                status_code=303,
            )
        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        today = utcnow_naive().date()
        now_na = utcnow_naive()
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
        return core.templates.TemplateResponse(
            request,
            "admin_report_print_summary.html",
            {
                "center": center,
                "paid_revenue_today": paid_revenue_today,
                "sessions_scheduled_today": sessions_scheduled_today,
                "bookings_active_today": bookings_active_today,
                "subs_expiring_7d": int(subs_7),
                "pending_stale_8d": pending_stale,
                "failed_7d": failed_7d,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )


    @router.post("/admin/reports/email-summary")
    def admin_reports_email_summary(request: Request, db: Session = Depends(get_db)):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_can_report_health(user=user, user_has_permission_fn=user_has_permission):
            return core._admin_redirect(core.ADMIN_MSG_REPORT_FORBIDDEN, return_section="section-reports")
        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        target = (center.report_digest_email or "").strip() if center else ""
        if not target:
            target = (user.email or "").strip()
        if not target:
            return core._admin_redirect("digest_email_failed", return_section="section-reports")
        today = utcnow_naive().date()
        now_na = utcnow_naive()
        rev = float(
            db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "paid",
                func.date(models.Payment.paid_at) == today,
            )
            .scalar()
            or 0.0
        )
        st = (
            int(
                db.query(func.count(models.YogaSession.id))
                .filter(models.YogaSession.center_id == cid, func.date(models.YogaSession.starts_at) == today)
                .scalar()
                or 0
            )
        )
        bk = (
            int(
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
        )
        html = (
            f"<html><body dir='rtl' style='font-family:Tahoma,sans-serif'>"
            f"<h2>ملخص يومي — {html_escape(center.name if center else '')}</h2>"
            f"<p>التاريخ: {today.isoformat()}</p>"
            f"<ul>"
            f"<li>جلسات مجدولة اليوم: {st}</li>"
            f"<li>حجوزات نشطة اليوم: {bk}</li>"
            f"<li>إيراد مدفوع اليوم: {rev:.2f} SAR</li>"
            f"</ul>"
            f"<p><a href='/admin/reports/print-summary'>صفحة ملخص للطباعة</a></p>"
            f"</body></html>"
        )
        plain = f"ملخص {center.name if center else ''}\nجلسات: {st}\nحجوزات: {bk}\nإيراد: {rev:.2f} SAR\n"
        ok, err = send_mail_with_attachments(
            to_email=target,
            subject=f"ملخص تشغيلي — {center.name if center else 'Maestro'} — {today.isoformat()}",
            body=plain,
            html_body=html,
        )
        log_security_event(
            "admin_digest_email",
            request,
            "success" if ok else "failed",
            email=user.email,
            details={"target": target, "err": err[:120] if err else ""},
        )
        return core._admin_redirect("digest_email_sent" if ok else "digest_email_failed", return_section="section-reports")


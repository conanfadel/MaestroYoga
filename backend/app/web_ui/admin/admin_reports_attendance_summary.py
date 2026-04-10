"""Session attendance, daily print summary, email digest — HTML routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ... import models
from ...database import get_db
from ...mailer import send_mail_with_attachments
from ...rbac import user_has_permission
from ...security_audit import log_security_event
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...admin_report_helpers import user_can_report_health
from ...web_shared import _url_with_params

from .admin_reports_attendance_summary_data import (
    build_digest_mail_parts,
    build_print_summary_template_context,
    fetch_daily_digest_core_metrics,
    load_session_attendance_template_context,
)


def register_admin_report_attendance_summary_routes(router: APIRouter) -> None:
    from .. import impl_state as core

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
        ctx = load_session_attendance_template_context(db, cid, session_id)
        if ctx is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return core.templates.TemplateResponse(request, "admin_session_attendance.html", ctx)

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
        ctx = build_print_summary_template_context(db, cid)
        return core.templates.TemplateResponse(request, "admin_report_print_summary.html", ctx)

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
        rev, st, bk = fetch_daily_digest_core_metrics(db, cid)
        subject, plain, html = build_digest_mail_parts(center, today, rev, st, bk)
        ok, err = send_mail_with_attachments(
            to_email=target,
            subject=subject,
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

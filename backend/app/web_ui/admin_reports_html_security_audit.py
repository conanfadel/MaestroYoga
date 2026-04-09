"""Admin HTML report: security audit log (HTML view)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..admin_report_helpers import report_period_to_range
from ..database import get_db
from ..rbac import user_has_permission
from ..time_utils import utcnow_naive
from ..web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_security_audit_routes(router: APIRouter) -> None:
    from . import impl_state as core

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

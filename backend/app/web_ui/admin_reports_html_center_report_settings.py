"""POST: center report settings (goals, VAT, digest email)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import models
from ..admin_report_helpers import parse_optional_non_negative_float, parse_optional_non_negative_int
from ..database import get_db
from ..rbac import user_has_permission
from ..security_audit import log_security_event
from ..tenant_utils import require_user_center_id


def register_admin_report_html_center_report_settings_routes(router: APIRouter) -> None:
    from . import impl_state as core

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

"""Admin HTML report: operational insights (route + data layer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import models
from ..admin_report_helpers import can_access_report_kind, report_period_to_range
from ..database import get_db
from ..rbac import user_has_permission
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..web_shared import _url_with_params

from .admin_reports_html_insights_data import build_insights_template_context


def register_admin_report_html_insights_routes(router: APIRouter) -> None:
    from . import impl_state as core

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
        ctx = build_insights_template_context(
            db=db,
            cid=cid,
            center=center,
            d0=d0,
            d1=d1,
            period=period,
            range_label=range_label,
            range_err=range_err,
            date_from=date_from,
            date_to=date_to,
        )
        return core.templates.TemplateResponse(request, "admin_report_insights.html", ctx)

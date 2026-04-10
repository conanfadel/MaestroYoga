"""Admin HTML report: light health / ops indicators."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models
from ...admin_report_helpers import can_access_report_kind
from ...database import get_db
from ...rbac import user_has_permission
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_health_routes(router: APIRouter) -> None:
    from .. import impl_state as core

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

"""Admin HTML report: expiring subscriptions."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models
from ...admin_report_helpers import build_subscription_report_rows, can_access_report_kind
from ...database import get_db
from ...rbac import user_has_permission
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_subscriptions_routes(router: APIRouter) -> None:
    from .. import impl_state as core

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
                url=_url_with_params("/admin/dashboard", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="subscriptions", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin/dashboard", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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

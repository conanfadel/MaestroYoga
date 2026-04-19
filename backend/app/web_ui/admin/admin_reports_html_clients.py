"""Admin HTML report: new vs returning clients."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models
from ...admin_export_helpers import clients_new_returning_for_range
from ...admin_report_helpers import can_access_report_kind, report_period_to_range, report_previous_period_range
from ...booking_utils import ACTIVE_BOOKING_STATUSES
from ...database import get_db
from ...rbac import user_has_permission
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_clients_routes(router: APIRouter) -> None:
    from .. import impl_state as core

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
                url=_url_with_params("/admin/dashboard", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="clients", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin/dashboard", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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

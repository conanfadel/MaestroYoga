"""Admin HTML report: stale pending payments alerts."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ... import models
from ...admin_report_helpers import can_access_report_kind
from ...database import get_db
from ...rbac import user_has_permission
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_pending_alerts_routes(router: APIRouter) -> None:
    from .. import impl_state as core

    @router.get("/admin/reports/pending-alerts", response_class=HTMLResponse)
    def admin_report_pending_alerts(
        request: Request,
        stale_minutes: int = 60,
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
        if not can_access_report_kind(user=user, kind="health", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
                status_code=303,
            )

        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        stale_minutes = max(15, min(7 * 24 * 60, int(stale_minutes or 60)))
        now = utcnow_naive()
        cutoff = now - timedelta(minutes=stale_minutes)

        rows = (
            db.query(models.Payment)
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "pending",
                models.Payment.created_at <= cutoff,
            )
            .order_by(models.Payment.created_at.asc())
            .limit(400)
            .all()
        )
        alerts: list[dict] = []
        for p in rows:
            client = db.get(models.Client, p.client_id)
            booking = db.get(models.Booking, p.booking_id) if p.booking_id else None
            age_min = max(0, int((now - (p.created_at or now)).total_seconds() // 60))
            alerts.append(
                {
                    "payment_id": int(p.id),
                    "created_at": _fmt_dt(p.created_at),
                    "age_min": age_min,
                    "amount": float(p.amount or 0),
                    "currency": (p.currency or "SAR").upper(),
                    "payment_method": p.payment_method or "-",
                    "provider_ref": p.provider_ref or "-",
                    "client_name": (client.full_name if client else "-"),
                    "client_email": (client.email if client else "-"),
                    "booking_id": int(booking.id) if booking else None,
                    "booking_status": (booking.status if booking else "-"),
                }
            )

        return core.templates.TemplateResponse(
            request,
            "admin_report_pending_alerts.html",
            {
                "center": center,
                "generated_at": _fmt_dt(now),
                "stale_minutes": stale_minutes,
                "cutoff_at": _fmt_dt(cutoff),
                "alerts": alerts,
            },
        )

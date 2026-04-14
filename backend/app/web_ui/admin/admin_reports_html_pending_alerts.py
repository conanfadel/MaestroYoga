"""Admin HTML report: stale pending payments alerts."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ... import models
from ...admin_report_helpers import can_access_report_kind
from ...database import get_db
from ...rbac import user_has_permission
from ...security_audit import log_security_event
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive
from ...web_shared import _fmt_dt, _url_with_params


def register_admin_report_html_pending_alerts_routes(router: APIRouter) -> None:
    from .. import impl_state as core

    def _ensure_health_access(request: Request, db: Session):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return None, redirect
        assert user is not None
        if (user.role or "") == "trainer":
            return None, RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="health", user_has_permission_fn=user_has_permission):
            return None, RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
                status_code=303,
            )
        return user, None

    def _resolve_single_pending_payment(db: Session, cid: int, payment_id: int) -> tuple[str, int | None]:
        p = db.get(models.Payment, int(payment_id))
        if not p or int(p.center_id) != int(cid):
            return "not_found", None
        if (p.status or "").lower() != "pending":
            return "not_pending", int(p.id)
        p.status = "failed"
        booking_id = None
        if p.booking_id:
            b = db.get(models.Booking, p.booking_id)
            if b and (b.status or "").lower() == "pending_payment":
                b.status = "cancelled"
            booking_id = int(p.booking_id)
        return "resolved", booking_id

    @router.post("/admin/reports/pending-alerts/resolve")
    def admin_report_pending_alerts_resolve(
        request: Request,
        payment_id: int = Form(...),
        stale_minutes: int = Form(60),
        db: Session = Depends(get_db),
    ):
        user, redirect = _ensure_health_access(request, db)
        if redirect:
            return redirect
        assert user is not None
        cid = require_user_center_id(user)
        stale_minutes = max(15, min(7 * 24 * 60, int(stale_minutes or 60)))
        status, booking_id = _resolve_single_pending_payment(db, cid, int(payment_id))
        if status == "not_found":
            return RedirectResponse(
                url=_url_with_params(
                    "/admin/reports/pending-alerts",
                    stale_minutes=str(stale_minutes),
                    msg="pending_alert_not_found",
                ),
                status_code=303,
            )
        if status == "not_pending":
            return RedirectResponse(
                url=_url_with_params(
                    "/admin/reports/pending-alerts",
                    stale_minutes=str(stale_minutes),
                    msg="pending_alert_already_resolved",
                ),
                status_code=303,
            )
        db.commit()
        log_security_event(
            "admin_pending_payment_resolved",
            request,
            "success",
            email=user.email,
            details={
                "center_id": int(cid),
                "payment_id": int(payment_id),
                "booking_id": booking_id,
                "stale_minutes": int(stale_minutes),
            },
        )
        return RedirectResponse(
            url=_url_with_params(
                "/admin/reports/pending-alerts",
                stale_minutes=str(stale_minutes),
                msg="pending_alert_resolved",
            ),
            status_code=303,
        )

    @router.post("/admin/reports/pending-alerts/resolve-batch")
    def admin_report_pending_alerts_resolve_batch(
        request: Request,
        payment_ids: str = Form(""),
        stale_minutes: int = Form(60),
        db: Session = Depends(get_db),
    ):
        user, redirect = _ensure_health_access(request, db)
        if redirect:
            return redirect
        assert user is not None
        cid = require_user_center_id(user)
        stale_minutes = max(15, min(7 * 24 * 60, int(stale_minutes or 60)))
        ids: list[int] = []
        for raw in (payment_ids or "").split(","):
            s = raw.strip()
            if s.isdigit():
                ids.append(int(s))
        ids = list(dict.fromkeys(ids))[:200]
        if not ids:
            return RedirectResponse(
                url=_url_with_params(
                    "/admin/reports/pending-alerts",
                    stale_minutes=str(stale_minutes),
                    msg="pending_alert_batch_empty",
                ),
                status_code=303,
            )

        resolved = 0
        skipped_not_pending = 0
        skipped_not_found = 0
        booking_ids: list[int] = []
        for pid in ids:
            status, booking_id = _resolve_single_pending_payment(db, cid, pid)
            if status == "resolved":
                resolved += 1
                if booking_id:
                    booking_ids.append(int(booking_id))
            elif status == "not_pending":
                skipped_not_pending += 1
            else:
                skipped_not_found += 1
        db.commit()
        log_security_event(
            "admin_pending_payment_resolved_batch",
            request,
            "success",
            email=user.email,
            details={
                "center_id": int(cid),
                "resolved_count": resolved,
                "skipped_not_pending": skipped_not_pending,
                "skipped_not_found": skipped_not_found,
                "payment_ids": ids,
                "booking_ids": booking_ids[:100],
                "stale_minutes": int(stale_minutes),
            },
        )
        msg = "pending_alert_batch_done" if resolved else "pending_alert_batch_none_resolved"
        return RedirectResponse(
            url=_url_with_params(
                "/admin/reports/pending-alerts",
                stale_minutes=str(stale_minutes),
                msg=msg,
            ),
            status_code=303,
        )

    @router.get("/admin/reports/pending-alerts", response_class=HTMLResponse)
    def admin_report_pending_alerts(
        request: Request,
        stale_minutes: int = 60,
        payment_method: str = "",
        provider_ref: str = "",
        db: Session = Depends(get_db),
    ):
        user, redirect = _ensure_health_access(request, db)
        if redirect:
            return redirect
        assert user is not None

        cid = require_user_center_id(user)
        center = db.get(models.Center, cid)
        stale_minutes = max(15, min(7 * 24 * 60, int(stale_minutes or 60)))
        payment_method = (payment_method or "").strip()[:64]
        provider_ref = (provider_ref or "").strip()[:120]
        now = utcnow_naive()
        cutoff = now - timedelta(minutes=stale_minutes)

        q = db.query(models.Payment).filter(
            models.Payment.center_id == cid,
            models.Payment.status == "pending",
            models.Payment.created_at <= cutoff,
        )
        if payment_method:
            q = q.filter(models.Payment.payment_method == payment_method)
        if provider_ref:
            q = q.filter(models.Payment.provider_ref.ilike(f"%{provider_ref}%"))
        rows = q.order_by(models.Payment.created_at.asc()).limit(400).all()
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
                "payment_method": payment_method,
                "provider_ref": provider_ref,
                "cutoff_at": _fmt_dt(cutoff),
                "alerts": alerts,
                "msg": (request.query_params.get("msg") or "").strip(),
            },
        )

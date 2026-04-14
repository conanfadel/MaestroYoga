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
        overdue_cutoff = utcnow_naive() - timedelta(minutes=10)
        pending_overdue = int(
            db.query(func.count(models.Payment.id))
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "pending",
                models.Payment.created_at < overdue_cutoff,
            )
            .scalar()
            or 0
        )
        paid_rows = (
            db.query(models.Payment)
            .filter(
                models.Payment.center_id == cid,
                models.Payment.status == "paid",
                models.Payment.created_at.isnot(None),
                models.Payment.paid_at.isnot(None),
                models.Payment.created_at >= (utcnow_naive() - timedelta(days=7)),
            )
            .all()
        )
        settle_minutes: list[float] = []
        for p in paid_rows:
            try:
                mins = max(0.0, float((p.paid_at - p.created_at).total_seconds()) / 60.0)
                settle_minutes.append(mins)
            except Exception:
                continue
        settle_minutes.sort()
        avg_settle_minutes = round(sum(settle_minutes) / len(settle_minutes), 2) if settle_minutes else 0.0
        p95_settle_minutes = 0.0
        if settle_minutes:
            idx = int(round(0.95 * (len(settle_minutes) - 1)))
            p95_settle_minutes = round(settle_minutes[idx], 2)
        webhook_failed_24h = int(
            db.query(func.count(models.SecurityAuditEvent.id))
            .filter(
                models.SecurityAuditEvent.event_type == "payment_webhook_invalid",
                models.SecurityAuditEvent.created_at >= (utcnow_naive() - timedelta(hours=24)),
            )
            .scalar()
            or 0
        )
        delay_alerts_24h = int(
            db.query(func.count(models.SecurityAuditEvent.id))
            .filter(
                models.SecurityAuditEvent.event_type == "payment_webhook_delay",
                models.SecurityAuditEvent.created_at >= (utcnow_naive() - timedelta(hours=24)),
            )
            .scalar()
            or 0
        )
        expiring_7d = int(
            db.query(func.count(models.ClientSubscription.id))
            .join(models.SubscriptionPlan, models.SubscriptionPlan.id == models.ClientSubscription.plan_id)
            .filter(
                models.SubscriptionPlan.center_id == cid,
                models.ClientSubscription.status == "active",
                models.ClientSubscription.end_date >= utcnow_naive(),
                models.ClientSubscription.end_date <= (utcnow_naive() + timedelta(days=7)),
            )
            .scalar()
            or 0
        )
        expired_30d = int(
            db.query(func.count(models.ClientSubscription.id))
            .join(models.SubscriptionPlan, models.SubscriptionPlan.id == models.ClientSubscription.plan_id)
            .filter(
                models.SubscriptionPlan.center_id == cid,
                models.ClientSubscription.end_date >= (utcnow_naive() - timedelta(days=30)),
                models.ClientSubscription.end_date < utcnow_naive(),
            )
            .scalar()
            or 0
        )

        return core.templates.TemplateResponse(
            request,
            "admin_report_health.html",
            {
                "center": center,
                "failed_7d": failed_7d,
                "failed_30d": failed_30d,
                "pending_payments_open": pending_n,
                "pending_overdue_10m": pending_overdue,
                "blocked_ips_active": blocked_ips,
                "avg_settle_minutes_7d": avg_settle_minutes,
                "p95_settle_minutes_7d": p95_settle_minutes,
                "webhook_failed_24h": webhook_failed_24h,
                "webhook_delay_alerts_24h": delay_alerts_24h,
                "subscriptions_expiring_7d": expiring_7d,
                "subscriptions_expired_30d": expired_30d,
                "generated_at": _fmt_dt(utcnow_naive()),
            },
        )

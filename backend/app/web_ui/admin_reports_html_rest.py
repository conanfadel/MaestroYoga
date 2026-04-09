"""Admin HTML reports: clients, subscriptions, health, security audit; center report settings POST."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, case, desc, func
from sqlalchemy.orm import Session

from .. import models
from ..admin_export_helpers import clients_new_returning_for_range
from ..admin_report_helpers import (
    build_subscription_report_rows,
    can_access_report_kind,
    effective_vat_percent_for_center,
    parse_optional_non_negative_float,
    parse_optional_non_negative_int,
    payment_method_label_ar,
    report_period_to_range,
    report_previous_period_range,
    vat_inclusive_breakdown,
)
from ..booking_utils import ACTIVE_BOOKING_STATUSES
from ..database import get_db
from ..rbac import user_has_permission
from ..security_audit import log_security_event
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..web_shared import _fmt_dt, _url_with_params

def register_admin_report_html_rest_routes(router: APIRouter) -> None:
    from . import impl_state as core

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
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="clients", user_has_permission_fn=user_has_permission):
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
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_TRAINER_ADMIN_FORBIDDEN),
                status_code=303,
            )
        if not can_access_report_kind(user=user, kind="subscriptions", user_has_permission_fn=user_has_permission):
            return RedirectResponse(
                url=_url_with_params("/admin", msg=core.ADMIN_MSG_REPORT_FORBIDDEN),
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



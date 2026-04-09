"""Small dict builders for admin dashboard insight cards, brief, exports, and loyalty thresholds."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks_kpi import AdminKpiCounts


def build_admin_insight_cards(
    dash_home: str, kpi: AdminKpiCounts, schedule_conflicts: Sequence[Any]
) -> list[dict[str, str]]:
    admin_insights: list[dict[str, str]] = []
    if kpi.sessions_today_no_bookings:
        admin_insights.append(
            {
                "label": f"جلسات اليوم بلا حجوزات نشطة: {kpi.sessions_today_no_bookings}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )
    if kpi.subs_expiring_7d:
        admin_insights.append(
            {
                "label": f"اشتراكات تنتهي خلال 7 أيام: {kpi.subs_expiring_7d}",
                "href": f"{dash_home}#section-plans",
                "kind": "info",
            }
        )
    if kpi.public_users_unverified_count:
        admin_insights.append(
            {
                "label": f"مستخدمون غير موثّقين (عام): {kpi.public_users_unverified_count}",
                "href": f"{dash_home}#section-public-users",
                "kind": "info",
            }
        )
    if schedule_conflicts:
        admin_insights.append(
            {
                "label": f"تضارب جدولة في نفس الغرفة: {len(schedule_conflicts)}",
                "href": f"{dash_home}#section-sessions",
                "kind": "warn",
            }
        )
    if kpi.pending_payments_stale_8d:
        admin_insights.append(
            {
                "label": f"معلّقات قديمة (+8 أيام): {kpi.pending_payments_stale_8d}",
                "href": "/admin/reports/health",
                "kind": "warn",
            }
        )
    if kpi.failed_payments_7d:
        admin_insights.append(
            {
                "label": f"مدفوعات فاشلة في آخر 7 أيام: {kpi.failed_payments_7d}",
                "href": "/admin/reports/health",
                "kind": "warn",
            }
        )
    return admin_insights


def build_morning_brief_dict(kpi: AdminKpiCounts, paid_revenue_today: float) -> dict[str, Any]:
    return {
        "sessions_today": kpi.sessions_scheduled_today,
        "bookings_today": kpi.bookings_active_today,
        "revenue_today": float(paid_revenue_today or 0),
        "pending_stale_8d": kpi.pending_payments_stale_8d,
        "failed_7d": kpi.failed_payments_7d,
        "subs_expiring_7d": kpi.subs_expiring_7d,
    }


def build_data_export_urls(payment_date_from: str, payment_date_to: str) -> tuple[dict[str, str], str, str]:
    export_pay_params: dict[str, str] = {}
    pf = (payment_date_from or "").strip()[:32]
    pt = (payment_date_to or "").strip()[:32]
    if pf:
        export_pay_params[_s.ADMIN_QP_PAYMENT_DATE_FROM] = pf
    if pt:
        export_pay_params[_s.ADMIN_QP_PAYMENT_DATE_TO] = pt
    data_export_urls = {
        "clients": "/admin/export/clients.csv",
        "bookings": "/admin/export/bookings.csv",
        "payments": _s._url_with_params("/admin/export/payments.csv", **export_pay_params)
        if export_pay_params
        else "/admin/export/payments.csv",
    }
    return data_export_urls, pf, pt


def build_loyalty_admin_dict(center: Any) -> dict[str, Any]:
    _env_b, _env_s, _env_g = _s.loyalty_thresholds()
    _eff_b, _eff_s, _eff_g = _s.effective_loyalty_thresholds(center)
    return {
        "env": {"bronze": _env_b, "silver": _env_s, "gold": _env_g},
        "effective": {"bronze": _eff_b, "silver": _eff_s, "gold": _eff_g},
    }

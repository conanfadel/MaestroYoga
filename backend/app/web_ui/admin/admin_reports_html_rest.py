"""Admin HTML reports: clients, subscriptions, health, security audit; center report settings POST."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_reports_html_center_report_settings import register_admin_report_html_center_report_settings_routes
from .admin_reports_html_clients import register_admin_report_html_clients_routes
from .admin_reports_html_health import register_admin_report_html_health_routes
from .admin_reports_html_pending_alerts import register_admin_report_html_pending_alerts_routes
from .admin_reports_html_security_audit import register_admin_report_html_security_audit_routes
from .admin_reports_html_subscriptions import register_admin_report_html_subscriptions_routes


def register_admin_report_html_rest_routes(router: APIRouter) -> None:
    register_admin_report_html_clients_routes(router)
    register_admin_report_html_subscriptions_routes(router)
    register_admin_report_html_health_routes(router)
    register_admin_report_html_pending_alerts_routes(router)
    register_admin_report_html_security_audit_routes(router)
    register_admin_report_html_center_report_settings_routes(router)

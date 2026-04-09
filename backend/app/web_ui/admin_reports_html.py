"""Admin HTML report pages (sessions, revenue, insights, clients, subscriptions, health, security audit, report settings)."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_reports_html_insights import register_admin_report_html_insights_routes
from .admin_reports_html_rest import register_admin_report_html_rest_routes
from .admin_reports_html_sessions_revenue import register_admin_report_html_sessions_revenue_routes


def register_admin_report_html_routes(router: APIRouter) -> None:
    """Register all admin HTML report GET/POST handlers."""
    register_admin_report_html_sessions_revenue_routes(router)
    register_admin_report_html_insights_routes(router)
    register_admin_report_html_rest_routes(router)

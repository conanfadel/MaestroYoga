"""Admin HTML reports: sessions and revenue (aggregates route modules)."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_reports_html_revenue import register_admin_report_html_revenue_routes
from .admin_reports_html_sessions import register_admin_report_html_sessions_routes


def register_admin_report_html_sessions_revenue_routes(router: APIRouter) -> None:
    register_admin_report_html_sessions_routes(router)
    register_admin_report_html_revenue_routes(router)

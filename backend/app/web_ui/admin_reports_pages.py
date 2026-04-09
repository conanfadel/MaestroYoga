"""Splits admin report pages across HTML reports vs attendance/summary routes."""

from fastapi import APIRouter

from .admin_reports_attendance_summary import register_admin_report_attendance_summary_routes
from .admin_reports_html import register_admin_report_html_routes


def register_admin_report_pages(router: APIRouter) -> None:
    register_admin_report_html_routes(router)
    register_admin_report_attendance_summary_routes(router)

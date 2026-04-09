"""Registers admin report HTML pages and CSV exports on the shared web UI router."""

from fastapi import APIRouter

from .admin_reports_exports import register_admin_report_exports
from .admin_reports_pages import register_admin_report_pages


def register_admin_report_routes(router: APIRouter) -> None:
    register_admin_report_pages(router)
    register_admin_report_exports(router)

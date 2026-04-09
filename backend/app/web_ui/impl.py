"""Web UI: FastAPI router aggregation."""

from fastapi import APIRouter

from .admin_reports import register_admin_report_routes
from .admin_routes import register_admin_routes
from .public_routes import register_public_routes

router = APIRouter(tags=["web"])

register_public_routes(router)
register_admin_routes(router)
register_admin_report_routes(router)

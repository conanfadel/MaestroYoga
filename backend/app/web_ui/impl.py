"""Web UI: FastAPI router aggregation."""

from fastapi import APIRouter

from .admin import register_admin_report_routes, register_admin_routes
from .public import register_public_routes

router = APIRouter(tags=["web"])

register_public_routes(router)
register_admin_routes(router)
register_admin_report_routes(router)

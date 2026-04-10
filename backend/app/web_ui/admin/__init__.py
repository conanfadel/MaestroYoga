"""Admin HTML routes (/admin/*, reports, exports)."""

from .admin_reports import register_admin_report_routes
from .admin_routes import register_admin_routes

__all__ = ["register_admin_report_routes", "register_admin_routes"]

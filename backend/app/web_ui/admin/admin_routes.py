"""Admin dashboard routes: composed from submodules."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_auth_routes import register_admin_auth_routes
from .admin_center_routes import register_admin_center_routes
from .admin_dashboard_routes import register_admin_dashboard_routes
from .admin_html_fragments_routes import register_admin_html_fragment_routes
from .admin_org_routes import register_admin_org_routes


def register_admin_routes(router: APIRouter) -> None:
    """Register /admin/* POST/GET handlers for dashboard operations."""
    register_admin_auth_routes(router)
    register_admin_dashboard_routes(router)
    register_admin_html_fragment_routes(router)
    register_admin_org_routes(router)
    register_admin_center_routes(router)

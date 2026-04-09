"""Center loyalty, branding, index page config, posts."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_center_routes_index_page import register_admin_center_index_page_routes
from .admin_center_routes_loyalty_branding import register_admin_center_loyalty_branding_routes
from .admin_center_routes_posts import register_admin_center_posts_routes


def register_admin_center_routes(router: APIRouter) -> None:
    """Center settings and posts."""
    register_admin_center_loyalty_branding_routes(router)
    register_admin_center_index_page_routes(router)
    register_admin_center_posts_routes(router)

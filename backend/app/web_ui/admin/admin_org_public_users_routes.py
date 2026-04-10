"""Admin org: Public user moderation and bulk actions."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_org_public_users_routes_bulk import register_admin_org_public_users_bulk_routes
from .admin_org_public_users_routes_moderation import register_admin_org_public_users_moderation_routes
from .admin_org_public_users_routes_toggle import register_admin_org_public_users_toggle_routes


def register_admin_org_public_users_routes(router: APIRouter) -> None:
    """Public user moderation and bulk actions."""
    register_admin_org_public_users_toggle_routes(router)
    register_admin_org_public_users_moderation_routes(router)
    register_admin_org_public_users_bulk_routes(router)

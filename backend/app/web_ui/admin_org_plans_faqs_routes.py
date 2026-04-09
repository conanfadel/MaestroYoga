"""Admin org: Plans and FAQ CRUD."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_org_faqs_routes import register_admin_org_faqs_routes
from .admin_org_plans_routes import register_admin_org_plans_routes


def register_admin_org_plans_faqs_routes(router: APIRouter) -> None:
    """Plans and FAQ CRUD."""
    register_admin_org_plans_routes(router)
    register_admin_org_faqs_routes(router)

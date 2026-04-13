"""Staff, security, public users, rooms, sessions, plans, FAQ CRUD."""

from __future__ import annotations

from fastapi import APIRouter

from .admin_org_plans_faqs_routes import register_admin_org_plans_faqs_routes
from .admin_org_public_users_routes import register_admin_org_public_users_routes
from .admin_org_rooms_routes import register_admin_org_rooms_routes
from .admin_org_sessions_routes import register_admin_org_sessions_routes
from .admin_org_staff_security_routes import register_admin_org_staff_security_routes
from .admin_org_training_routes import register_admin_org_training_routes


def register_admin_org_routes(router: APIRouter) -> None:
    """Organization and content management POST handlers."""
    register_admin_org_staff_security_routes(router)
    register_admin_org_public_users_routes(router)
    register_admin_org_rooms_routes(router)
    register_admin_org_sessions_routes(router)
    register_admin_org_training_routes(router)
    register_admin_org_plans_faqs_routes(router)

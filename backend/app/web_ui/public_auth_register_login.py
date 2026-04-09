"""Register, login, and logout routes for public users (aggregates submodules)."""

from __future__ import annotations

from fastapi import APIRouter

from .public_auth_login_logout import register_public_auth_login_logout_routes
from .public_auth_register import register_public_auth_register_routes


def register_public_auth_register_login_routes(router: APIRouter) -> None:
    register_public_auth_register_routes(router)
    register_public_auth_login_logout_routes(router)

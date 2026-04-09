"""Public account: register, login, profile, verification, password reset."""

from __future__ import annotations

from fastapi import APIRouter

from .public_auth_account import register_public_auth_account_routes
from .public_auth_password import register_public_auth_password_routes
from .public_auth_register_login import register_public_auth_register_login_routes
from .public_auth_verify import register_public_auth_verify_routes


def register_public_auth_routes(router: APIRouter) -> None:
    """Register, login, account, verify, forgot/reset password."""
    register_public_auth_register_login_routes(router)
    register_public_auth_account_routes(router)
    register_public_auth_verify_routes(router)
    register_public_auth_password_routes(router)

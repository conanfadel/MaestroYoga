"""Email verification pending page, resend, and verify-email link (aggregates submodules)."""

from __future__ import annotations

from fastapi import APIRouter

from .public_auth_verify_actions_routes import register_public_auth_verify_actions_routes
from .public_auth_verify_pending_routes import register_public_auth_verify_pending_routes


def register_public_auth_verify_routes(router: APIRouter) -> None:
    register_public_auth_verify_pending_routes(router)
    register_public_auth_verify_actions_routes(router)

"""Account profile update and soft-delete confirmation routes (aggregates submodules)."""

from __future__ import annotations

from fastapi import APIRouter

from .public_auth_account_delete import register_public_auth_account_delete_routes
from .public_auth_account_profile import register_public_auth_account_profile_routes


def register_public_auth_account_routes(router: APIRouter) -> None:
    register_public_auth_account_profile_routes(router)
    register_public_auth_account_delete_routes(router)

"""Public (customer-facing) HTML routes."""

from __future__ import annotations

from fastapi import APIRouter

from .public_auth_routes import register_public_auth_routes
from .public_browse_routes import register_public_browse_routes
from .public_checkout_status_routes import register_public_checkout_status_routes
from .public_commerce_routes import register_public_commerce_routes
from .public_feedback_routes import register_public_feedback_routes
from .public_index_routes import register_public_index_routes
from .public_subscribe_routes import register_public_subscribe_routes


def register_public_routes(router: APIRouter) -> None:
    """Register /index, /public/*, /news, /post, feedback, commerce, auth, subscribe."""
    register_public_index_routes(router)
    register_public_checkout_status_routes(router)
    register_public_browse_routes(router)
    register_public_feedback_routes(router)
    register_public_commerce_routes(router)
    register_public_auth_routes(router)
    register_public_subscribe_routes(router)

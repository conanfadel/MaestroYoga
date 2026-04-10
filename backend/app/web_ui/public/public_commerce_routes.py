"""Public booking: single session and cart checkout (aggregates submodules)."""

from __future__ import annotations

from fastapi import APIRouter

from .public_commerce_book_routes import register_public_commerce_book_routes
from .public_commerce_cart_routes import register_public_commerce_cart_routes


def register_public_commerce_routes(router: APIRouter) -> None:
    """Book session and cart checkout."""
    register_public_commerce_book_routes(router)
    register_public_commerce_cart_routes(router)

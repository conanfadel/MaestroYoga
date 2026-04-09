"""Public browse: content version JSON, news list, post detail (aggregates submodules)."""

from __future__ import annotations

from fastapi import APIRouter

from .public_browse_news_routes import register_public_browse_news_routes
from .public_browse_utils_routes import register_public_browse_utils_routes


def register_public_browse_routes(router: APIRouter) -> None:
    """Content version, news list, post detail."""
    register_public_browse_utils_routes(router)
    register_public_browse_news_routes(router)

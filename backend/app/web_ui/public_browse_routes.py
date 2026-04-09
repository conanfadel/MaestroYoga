"""Public content: version, feedback, news list, post detail (aggregates submodules)."""

from __future__ import annotations

from fastapi import APIRouter

from .public_browse_news_routes import register_public_browse_news_routes
from .public_browse_utils_routes import register_public_browse_utils_routes


def register_public_browse_routes(router: APIRouter) -> None:
    """Content version, feedback, news list, post detail."""
    register_public_browse_utils_routes(router)
    register_public_browse_news_routes(router)

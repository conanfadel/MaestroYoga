"""Server-rendered web UI (public pages + admin). Split across submodules for maintainability."""

from .router import router
from . import public_routes  # noqa: F401
from . import admin_routes  # noqa: F401

__all__ = ["router"]

"""JSON REST API router (mounted at / and /api/v1 from main)."""

from __future__ import annotations

from fastapi import APIRouter

from . import routes_auth, routes_core, routes_org, routes_payments, routes_seed

api_router = APIRouter(tags=["api"])

routes_core.register_routes(api_router)
routes_auth.register_routes(api_router)
routes_org.register_routes(api_router)
routes_payments.register_routes(api_router)
routes_seed.register_routes(api_router)

__all__ = ["api_router"]

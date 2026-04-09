"""Mobile client discovery: /api/v1/meta."""

from __future__ import annotations

from fastapi import APIRouter


def build_api_v1_meta_router(*, server_version: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["api-v1"])

    @router.get("/meta")
    def api_v1_meta():
        """نقطة دخول موحّدة لتطبيق أندرويد: إصدار الـ API وروابط التوثيق."""
        return {
            "api_version": "1",
            "app": "Maestro Yoga",
            "server_version": server_version,
            "openapi_json": "/openapi.json",
            "docs": "/docs",
            "client_hint": "أرسل الرأس X-App-Version (مثل 1.0.0) ليُعاد في X-App-Version-Accepted.",
        }

    return router

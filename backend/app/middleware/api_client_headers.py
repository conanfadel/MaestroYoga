"""API version header and optional X-App-Version echo for mobile / WebView clients."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ApiClientHeadersMiddleware(BaseHTTPMiddleware):
    """إصدار واجهة REST (X-API-Version) واعتماد رأس إصدار تطبيق العميل (أندرويد/WebView)."""

    async def dispatch(self, request: Request, call_next):
        raw = (request.headers.get("X-App-Version") or "").strip()
        av = raw[:64] if raw else ""
        if av:
            request.state.app_version = av
        response: Response = await call_next(request)
        response.headers["X-API-Version"] = "1"
        if av:
            response.headers["X-App-Version-Accepted"] = av
        return response

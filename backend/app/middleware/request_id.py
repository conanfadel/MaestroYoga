"""Attach X-Request-ID for tracing (logs, mobile, support)."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """يُمرَّر معرّف الطلب في الرؤوس (X-Request-ID) للتتبع والجوال والسجلات."""

    async def dispatch(self, request: Request, call_next):
        incoming = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or str(uuid.uuid4())
        )
        rid = incoming.strip()[:128] or str(uuid.uuid4())
        request.state.request_id = rid
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

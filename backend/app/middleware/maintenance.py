"""503 maintenance mode with JSON for API clients and HTML for browsers."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

_MAINTENANCE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="theme-color" content="#c5a059"/>
  <title>صيانة — Maestro Yoga</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; min-height: 100dvh; display: grid; place-items: center;
           background: #fafcfb; color: #2d3436; padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left)); }
    .box { text-align: center; max-width: 28rem; }
    h1 { font-size: 1.25rem; margin: 0 0 8px; }
    p { margin: 0; opacity: 0.85; }
  </style>
</head>
<body>
  <div class="box">
    <h1>جاري التحديث</h1>
    <p>نعتذر عن الإزعاج. نعود قريباً — يمكنك إعادة المحاولة بعد قليل.</p>
    <p style="margin-top:12px;font-size:0.85rem">Maintenance — please try again shortly.</p>
  </div>
</body>
</html>
"""


def maintenance_enabled() -> bool:
    return os.getenv("MAINTENANCE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _path_exempt_from_maintenance(path: str) -> bool:
    if path == "/health" or path.startswith("/health/"):
        return True
    if path == "/api/v1/health" or path.startswith("/api/v1/health/"):
        return True
    if path.startswith("/static/"):
        return True
    if path in {"/favicon.ico", "/openapi.json", "/docs", "/redoc"}:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    # webhooks للدفع يجب أن تبقى قابلة للوصول أثناء الصيانة
    if path.startswith("/payments/webhook"):
        return True
    return False


class MaintenanceMiddleware(BaseHTTPMiddleware):
    """يُعيد 503 عند MAINTENANCE_MODE=1 مع JSON للـ API و HTML للواجهة."""

    async def dispatch(self, request: Request, call_next):
        if not maintenance_enabled():
            return await call_next(request)
        path = request.url.path
        if _path_exempt_from_maintenance(path):
            return await call_next(request)

        accept = request.headers.get("accept") or ""
        accept_lower = accept.lower()
        first = accept_lower.split(",")[0].strip() if accept_lower else ""
        prefers_json = "application/json" in accept_lower and "text/html" not in first
        if prefers_json:
            return JSONResponse(
                {"error": "maintenance", "message": "الخدمة تحت الصيانة قصيراً.", "retry_after": 120},
                status_code=503,
                headers={"Retry-After": "120"},
            )
        return HTMLResponse(
            content=_MAINTENANCE_HTML,
            status_code=503,
            headers={"Retry-After": "120"},
        )

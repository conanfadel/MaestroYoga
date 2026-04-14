"""Per-IP sliding-window rate limit with stricter buckets for auth POST routes."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

_RL_LOCK = threading.Lock()
_RL_BUCKETS: dict[str, deque[float]] = defaultdict(deque)

_STRICT_AUTH_POST_PATHS = frozenset(
    {
        "/public/login",
        "/public/register",
        "/admin/login",
        "/public/forgot-password",
        "/public/reset-password",
        "/public/resend-verification",
    }
)


def rate_limit_middleware_enabled() -> bool:
    """معطّل تلقائياً أثناء pytest (RATE_LIMIT_ENABLED=0 في conftest) أو عبر البيئة."""
    v = os.getenv("RATE_LIMIT_ENABLED", "1").strip().lower()
    if v in {"0", "false", "no", "off"}:
        return False
    return v in {"", "1", "true", "yes", "on"}


def _rate_limit_window_sec() -> float:
    try:
        w = float(os.getenv("RATE_LIMIT_WINDOW_SEC", "60").strip())
    except ValueError:
        w = 60.0
    return max(5.0, min(w, 3600.0))


def _rate_limit_general_per_window() -> int:
    try:
        n = int(os.getenv("RATE_LIMIT_GENERAL_PER_WINDOW", "240").strip())
    except ValueError:
        n = 240
    return max(30, min(n, 50_000))


def _rate_limit_strict_per_window() -> int:
    try:
        n = int(os.getenv("RATE_LIMIT_STRICT_PER_WINDOW", "30").strip())
    except ValueError:
        n = 30
    return max(1, min(n, 5_000))


def clear_rate_limit_buckets_for_tests() -> None:
    """يُفرغ عدّادات الاختبار بين الحالات (وحدات الاختبار فقط)."""
    with _RL_LOCK:
        _RL_BUCKETS.clear()


def _rl_prune(dq: deque[float], now: float, window: float) -> None:
    while dq and dq[0] < now - window:
        dq.popleft()


def _client_ip_for_rate_limit(request: Request) -> str:
    trust = os.getenv("RATE_LIMIT_TRUST_X_FORWARDED_FOR", "").strip().lower() in {"1", "true", "yes", "on"}
    if trust:
        xff = (request.headers.get("x-forwarded-for") or "").strip()
        if xff:
            return xff.split(",")[0].strip()[:128] or "unknown"
    if request.client and request.client.host:
        return (request.client.host or "").strip()[:128] or "unknown"
    return "unknown"


def _path_exempt_from_rate_limit(path: str, method: str) -> bool:
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
    if path.startswith("/payments/webhook"):
        return True
    # لوحة الإدارة صفحة واحدة ثقيلة + تحميلات متتابعة؛ لا تُحسب ضمن الحد العام لتفادي 429 ورسالة «انتظر».
    m = (method or "GET").upper()
    if m in {"GET", "HEAD"} and (path == "/admin" or path.startswith("/admin/")):
        return True
    return False


def _is_strict_auth_post(path: str, method: str) -> bool:
    if method.upper() != "POST":
        return False
    if path in _STRICT_AUTH_POST_PATHS:
        return True
    if path.endswith("/auth/login") or path.endswith("/auth/register"):
        return True
    return False


def _rate_limit_bucket_key(request: Request) -> tuple[str, int]:
    """مفتاح التجميع والحد الأقصى: مسارات التحقق الصارمة مجمّعة لكل IP؛ الباقي لكل IP."""
    path = request.url.path
    method = request.method.upper()
    ip = _client_ip_for_rate_limit(request)
    if _is_strict_auth_post(path, method):
        return f"strict:{ip}", _rate_limit_strict_per_window()
    return f"general:{ip}", _rate_limit_general_per_window()


def _rate_limit_check(request: Request) -> tuple[bool, int, float]:
    """يعيد (مسموح، المتبقي التقريبي، نافذة الثواني)."""
    window = _rate_limit_window_sec()
    key, limit = _rate_limit_bucket_key(request)
    with _RL_LOCK:
        now = time.monotonic()
        dq = _RL_BUCKETS[key]
        _rl_prune(dq, now, window)
        if len(dq) >= limit:
            return False, 0, float(window)
        dq.append(now)
        _rl_prune(dq, now, window)
        remaining = limit - len(dq)
        return True, remaining, window


_RATE_LIMIT_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="theme-color" content="#c5a059"/>
  <title>طلبات كثيرة — Maestro Yoga</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; min-height: 100dvh; display: grid; place-items: center;
           background: #fafcfb; color: #2d3436; padding: 16px; }
    .box { text-align: center; max-width: 28rem; }
    h1 { font-size: 1.2rem; margin: 0 0 8px; }
    p { margin: 0; opacity: 0.88; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="box">
    <h1>تم تجاوز حد الطلبات</h1>
    <p>طلبات كثيرة من نفس العنوان. انتظر قليلاً ثم أعد المحاولة.</p>
    <p style="margin-top:10px;font-size:0.85rem">Too many requests — please try again shortly.</p>
  </div>
</body>
</html>
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """حد أقصى لعدد الطلبات لكل عنوان IP (نافذة زمنية قابلة للضبط). مسارات تسجيل الدخول والتسجيل أشدّ."""

    async def dispatch(self, request: Request, call_next):
        if not rate_limit_middleware_enabled():
            return await call_next(request)
        if request.method.upper() == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if _path_exempt_from_rate_limit(path, request.method):
            return await call_next(request)
        ok, remaining, window = _rate_limit_check(request)
        if ok:
            response = await call_next(request)
            if remaining >= 0:
                response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
            response.headers["X-RateLimit-Limit-Window"] = str(int(window))
            return response
        accept = request.headers.get("accept") or ""
        accept_lower = accept.lower()
        first = accept_lower.split(",")[0].strip() if accept_lower else ""
        prefers_json = "application/json" in accept_lower and "text/html" not in first
        retry_sec = max(1, min(int(window), 120))
        if prefers_json or path.startswith("/api/"):
            return JSONResponse(
                {
                    "error": "rate_limit",
                    "message": "تم تجاوز حد الطلبات. أعد المحاولة لاحقاً.",
                    "retry_after": retry_sec,
                },
                status_code=429,
                headers={"Retry-After": str(retry_sec)},
            )
        return HTMLResponse(
            content=_RATE_LIMIT_HTML,
            status_code=429,
            headers={"Retry-After": str(retry_sec)},
        )

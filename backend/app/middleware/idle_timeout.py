"""Sliding idle timeout for browser sessions (public + admin) via httponly activity cookies."""

from __future__ import annotations

import os
import time
from typing import Callable

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from ..security.config import (
    APP_ENV,
    IDLE_COOKIE_ADMIN,
    IDLE_COOKIE_PUBLIC,
    IDLE_SESSION_TIMEOUT_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
    PUBLIC_JWT_SECRET,
)
from ..web_shared import _cookie_secure_flag

_PUBLIC_SESSION_COOKIE = "public_access_token"


def _idle_seconds() -> int:
    return max(60, int(IDLE_SESSION_TIMEOUT_MINUTES) * 60)


def _skip_path(path: str) -> bool:
    if path.startswith("/static/"):
        return True
    if path == "/health" or path.startswith("/health/"):
        return True
    if path == "/api/v1/health" or path.startswith("/api/v1/health/"):
        return True
    if path.startswith("/payments/webhook"):
        return True
    if path in {"/favicon.ico", "/openapi.json", "/docs", "/redoc", "/sw.js"}:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


def _decode_public_session(token: str) -> bool:
    try:
        payload = jwt.decode(token, PUBLIC_JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("purpose") == "public_session"
    except (JWTError, ValueError, TypeError):
        return False


def _decode_staff_access(token: str) -> bool:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("type") in (None, "access")
    except (JWTError, ValueError, TypeError):
        return False


def _stamp_idle(response: Response, cookie_name: str, secure: bool) -> None:
    response.set_cookie(
        key=cookie_name,
        value=str(int(time.time())),
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=60 * 60 * 24 * 8,
        path="/",
    )


class IdleTimeoutMiddleware(BaseHTTPMiddleware):
    """If JWT session cookie is present and idle cookie exceeds threshold, redirect to logout."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if APP_ENV in {"test", "testing"}:
            return await call_next(request)
        if os.getenv("DISABLE_IDLE_TIMEOUT", "").strip().lower() in {"1", "true", "yes", "on"}:
            return await call_next(request)
        path = request.url.path
        if _skip_path(path):
            return await call_next(request)

        secure = _cookie_secure_flag(request)

        idle_max = _idle_seconds()
        now = int(time.time())

        pub_tok = request.cookies.get(_PUBLIC_SESSION_COOKIE)
        if pub_tok and _decode_public_session(pub_tok):
            last_raw = request.cookies.get(IDLE_COOKIE_PUBLIC)
            if last_raw:
                try:
                    last = int(last_raw)
                except ValueError:
                    last = 0
                if last > 0 and (now - last) > idle_max:
                    if path.startswith("/api/"):
                        return JSONResponse(
                            {"error": "session_idle", "message": "انتهت الجلسة لعدم النشاط."},
                            status_code=401,
                        )
                    return RedirectResponse(url="/public/logout?reason=idle", status_code=303)

        adm_tok = request.cookies.get("access_token")
        if adm_tok and _decode_staff_access(adm_tok):
            last_raw = request.cookies.get(IDLE_COOKIE_ADMIN)
            if last_raw:
                try:
                    last = int(last_raw)
                except ValueError:
                    last = 0
                if last > 0 and (now - last) > idle_max:
                    if path.startswith("/api/"):
                        return JSONResponse(
                            {"error": "session_idle", "message": "انتهت الجلسة لعدم النشاط."},
                            status_code=401,
                        )
                    return RedirectResponse(url="/admin/logout?reason=idle", status_code=303)

        response = await call_next(request)

        if isinstance(response, Response) and response.status_code < 400:
            if pub_tok and _decode_public_session(pub_tok):
                _stamp_idle(response, IDLE_COOKIE_PUBLIC, secure)
            if adm_tok and _decode_staff_access(adm_tok):
                _stamp_idle(response, IDLE_COOKIE_ADMIN, secure)

        return response

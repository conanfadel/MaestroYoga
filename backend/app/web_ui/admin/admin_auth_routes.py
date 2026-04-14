"""Admin login/logout HTML routes."""

from __future__ import annotations

import time

from fastapi import APIRouter

from .. import impl_state as _s
from ...security.config import IDLE_COOKIE_ADMIN


def register_admin_auth_routes(router: APIRouter) -> None:
    """Login page, POST login, logout."""

    @router.get("/admin/login", response_class=_s.HTMLResponse)
    def admin_login_page(request: _s.Request, db: _s.Session = _s.Depends(_s.get_db)):
        # Seed demo data only in explicitly allowed environments.
        if _s.should_auto_seed_demo_data():
            _s.ensure_demo_data(db)
        return _s.templates.TemplateResponse(request, "admin_login.html", {})
    
    
    @router.post("/admin/login")
    def admin_login(
        request: _s.Request,
        email: str = _s.Form(...),
        password: str = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        email_norm = (email or "").strip().lower()
        user = db.query(_s.models.User).filter(_s.models.User.email == email_norm).first()
        if not user or not _s.verify_password(password, user.password_hash):
            _s.log_security_event(
                "admin_login",
                request,
                "invalid_credentials",
                email=email_norm,
            )
            return _s.RedirectResponse(url="/admin/login?error=1", status_code=303)
        if user.role not in _s.CENTER_ADMIN_LOGIN_ROLES:
            _s.log_security_event(
                "admin_login",
                request,
                "forbidden_role",
                email=user.email,
            )
            return _s.RedirectResponse(url="/admin/login?error=role", status_code=303)
    
        _s.log_security_event("admin_login", request, "success", email=user.email)
        token = _s.create_access_token(user.id)
        response = _s.RedirectResponse(url="/admin", status_code=303)
        secure = _s._cookie_secure_flag(request)
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite="lax",
            secure=secure,
            max_age=60 * 60 * 12,
            path="/",
        )
        response.set_cookie(
            key=IDLE_COOKIE_ADMIN,
            value=str(int(time.time())),
            httponly=True,
            samesite="lax",
            secure=secure,
            max_age=60 * 60 * 24 * 8,
            path="/",
        )
        return response

    def _admin_logout_response(*, msg: str | None) -> _s.RedirectResponse:
        q = "/admin/login" + (f"?msg={msg}" if msg else "")
        response = _s.RedirectResponse(url=q, status_code=303)
        response.delete_cookie("access_token", path="/")
        response.delete_cookie(IDLE_COOKIE_ADMIN, path="/")
        return response

    @router.get("/admin/logout")
    def admin_logout_get(reason: str | None = None):
        return _admin_logout_response(msg="idle_timeout" if reason == "idle" else None)

    @router.post("/admin/logout")
    def admin_logout():
        return _admin_logout_response(msg=None)

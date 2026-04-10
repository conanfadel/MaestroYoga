"""Admin login/logout HTML routes."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


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
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite="lax",
            secure=_s._cookie_secure_flag(request),
            max_age=60 * 60 * 12,
        )
        return response
    
    
    @router.post("/admin/logout")
    def admin_logout():
        response = _s.RedirectResponse(url="/admin/login", status_code=303)
        response.delete_cookie("access_token")
        return response

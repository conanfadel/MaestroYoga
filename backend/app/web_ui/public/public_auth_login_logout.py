"""Public user login GET/POST and logout."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_login_logout_routes(router: APIRouter) -> None:
    @router.get("/public/login", response_class=_s.HTMLResponse)
    def public_login_page(request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH):
        return _s.templates.TemplateResponse(
            request, "public_login.html", {"next": next, **_s._analytics_context("public_login")}
        )

    @router.post("/public/login")
    def public_login(
        request: _s.Request,
        email: str = _s.Form(...),
        password: str = _s.Form(...),
        next: str = _s.Form(_s.PUBLIC_INDEX_DEFAULT_PATH),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        safe_next = _s._sanitize_next_url(next)
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(next_url=safe_next, msg="ip_blocked")
        email_normalized = email.lower().strip()
        if _s.is_public_login_rate_limited(
            request=request,
            email=email_normalized,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            log_security_event_fn=_s.log_security_event,
        ):
            return _s._public_login_redirect(next_url=safe_next, msg="rate_limited")
        user = (
            db.query(_s.models.PublicUser)
            .filter(_s.models.PublicUser.email == email_normalized, _s.models.PublicUser.is_deleted.is_(False))
            .first()
        )
        if not user or not _s.verify_password(password, user.password_hash):
            _s.log_security_event("public_login", request, "invalid_credentials", email=email_normalized)
            return _s._public_login_redirect(next_url=safe_next, msg="invalid_credentials")
        if not user.is_active:
            _s.log_security_event("public_login", request, "inactive", email=email_normalized)
            return _s._public_login_redirect(next_url=safe_next, msg="inactive")

        token = _s.create_public_access_token(user.id)
        response = _s.RedirectResponse(
            url=_s.build_post_login_redirect_url(
                safe_next=safe_next,
                verification_required=_s._is_email_verification_required(),
                email_verified=bool(user.email_verified),
                url_with_params_fn=_s._url_with_params,
            ),
            status_code=303,
        )
        _s.set_public_auth_cookie(
            response=response,
            cookie_name=_s.PUBLIC_COOKIE_NAME,
            token=token,
            secure=_s._cookie_secure_flag(request),
        )
        _s.log_security_event(
            "public_login",
            request,
            "success",
            email=user.email,
            details={"email_verified": user.email_verified},
        )
        return response

    @router.get("/public/logout")
    def public_logout(reason: str | None = None):
        from ...security.config import IDLE_COOKIE_PUBLIC

        msg = "session_idle" if reason == "idle" else "logged_out"
        base = _s.PUBLIC_INDEX_DEFAULT_PATH
        joiner = "&" if "?" in base else "?"
        response = _s.RedirectResponse(url=f"{base}{joiner}msg={msg}", status_code=303)
        response.delete_cookie(_s.PUBLIC_COOKIE_NAME, path="/")
        response.delete_cookie(IDLE_COOKIE_PUBLIC, path="/")
        return response

"""Forgot password and reset-password routes."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_password_routes(router: APIRouter) -> None:
    @router.get("/public/forgot-password", response_class=_s.HTMLResponse)
    def public_forgot_password_page(request: _s.Request):
        return _s.templates.TemplateResponse(request, "public_forgot_password.html", _s._analytics_context("public_forgot_password"))
    
    
    @router.post("/public/forgot-password")
    def public_forgot_password(
        request: _s.Request,
        email: str = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(msg="ip_blocked")
        email_normalized = email.lower().strip()
        if _s.is_public_forgot_password_rate_limited(
            request=request,
            email=email_normalized,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            log_security_event_fn=_s.log_security_event,
        ):
            return _s.RedirectResponse(url="/public/forgot-password?msg=rate_limited", status_code=303)
    
        user = (
            db.query(_s.models.PublicUser)
            .filter(_s.models.PublicUser.email == email_normalized, _s.models.PublicUser.is_deleted.is_(False))
            .first()
        )
        mail_sent = False
        if user and user.is_active:
            reset_url = _s.build_reset_url(request, user)
            mail_sent, mail_info = _s.queue_password_reset_email(user.email, reset_url, full_name=user.full_name)
            if not mail_sent:
                _s.log_security_event(
                    "public_forgot_password",
                    request,
                    "mail_failed",
                    email=email_normalized,
                    details={"mail_error": mail_info[:200]},
                )
        _s.log_security_event("public_forgot_password", request, "accepted", email=email_normalized)
        # Keep response neutral, but surface delivery issue when sending fails for an existing account.
        if user and user.is_active and not mail_sent:
            why = _s.public_mail_fail_why_token(mail_info)
            fp = {"msg": "mail_failed"}
            if why:
                fp["why"] = why
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/forgot-password", **fp),
                status_code=303,
            )
        return _s.RedirectResponse(url="/public/forgot-password?msg=sent", status_code=303)
    
    
    @router.get("/public/reset-password", response_class=_s.HTMLResponse)
    def public_reset_password_page(request: _s.Request, token: str | None = None):
        raw = (token or "").strip()
        token_valid = False
        if raw:
            try:
                _s.decode_public_password_reset_token(raw)
                token_valid = True
            except _s.HTTPException:
                token_valid = False
        return _s.templates.TemplateResponse(
            request,
            "public_reset_password.html",
            {
                "token": raw if token_valid else "",
                "reset_token_missing": not raw,
                "reset_token_invalid": bool(raw) and not token_valid,
                **_s._analytics_context("public_reset_password"),
            },
        )
    
    
    @router.post("/public/reset-password")
    def public_reset_password(
        request: _s.Request,
        token: str = _s.Form(...),
        password: str = _s.Form(...),
        confirm_password: str = _s.Form(...),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(msg="ip_blocked")
        if _s.is_public_reset_password_rate_limited(
            request=request,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            log_security_event_fn=_s.log_security_event,
        ):
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/reset-password", token=token, msg="rate_limited"),
                status_code=303,
            )
        validation_msg = _s.reset_password_validation_error(
            password=password,
            confirm_password=confirm_password,
            is_strong_password_fn=_s._is_strong_public_password,
        )
        if validation_msg:
            _s.log_security_event("public_reset_password", request, validation_msg)
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/reset-password", token=token, msg=validation_msg),
                status_code=303,
            )
    
        try:
            payload = _s.decode_public_password_reset_token(token)
            user_id = int(payload.get("sub"))
        except (_s.HTTPException, TypeError, ValueError):
            _s.log_security_event("public_reset_password", request, "invalid_token")
            return _s._public_login_redirect(msg="invalid_reset_link")
        email = str(payload.get("email", "")).lower().strip()
        user = db.get(_s.models.PublicUser, user_id)
        if not user or user.email.lower() != email or user.is_deleted:
            _s.log_security_event("public_reset_password", request, "invalid_token")
            return _s._public_login_redirect(msg="invalid_reset_link")
    
        user.password_hash = _s.hash_password(password)
        user.is_active = True
        db.commit()
        _s.log_security_event("public_reset_password", request, "success", email=user.email)
        return _s._public_login_redirect(msg="password_reset_success")


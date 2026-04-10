"""Public user registration GET/POST."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_register_routes(router: APIRouter) -> None:
    @router.get("/public/register", response_class=_s.HTMLResponse)
    def public_register_page(request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH):
        safe_next = _s._sanitize_next_url(request.query_params.get("next") or next)
        return _s.templates.TemplateResponse(
            request,
            "public_register.html",
            {"next": safe_next, **_s._analytics_context("public_register")},
        )

    @router.post("/public/register")
    def public_register(
        request: _s.Request,
        full_name: str = _s.Form(...),
        email: str = _s.Form(...),
        country_code: str = _s.Form(...),
        phone: str = _s.Form(...),
        password: str = _s.Form(...),
        next: str = _s.Form(_s.PUBLIC_INDEX_DEFAULT_PATH),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        safe_next = _s._sanitize_next_url(next)
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(next_url=safe_next, msg="ip_blocked")
        email_normalized = email.lower().strip()
        full_name_normalized = full_name.strip()
        phone_normalized = _s._normalize_phone_with_country(country_code, phone)
        if (
            not full_name_normalized
            or not email_normalized
            or not password.strip()
            or not phone.strip()
            or not country_code.strip()
        ):
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/register", msg="required_fields", next=safe_next),
                status_code=303,
            )
        if phone_normalized is None:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/register", msg="invalid_phone", next=safe_next),
                status_code=303,
            )
        if _s.is_public_register_rate_limited(
            request=request,
            email=email_normalized,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            log_security_event_fn=_s.log_security_event,
        ):
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/register", msg="rate_limited", next=safe_next),
                status_code=303,
            )
        exists = db.query(_s.models.PublicUser).filter(_s.models.PublicUser.email == email_normalized).first()
        if exists and not exists.is_deleted:
            _s.log_security_event("public_register", request, "already_exists", email=email_normalized)
            return _s._public_login_redirect(msg="account_exists")
        phone_exists = (
            db.query(_s.models.PublicUser)
            .filter(_s.models.PublicUser.phone == phone_normalized, _s.models.PublicUser.is_deleted.is_(False))
            .first()
        )
        if phone_exists:
            _s.log_security_event("public_register", request, "phone_already_exists", email=email_normalized)
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/register", msg="phone_exists", next=safe_next),
                status_code=303,
            )
        if not _s._is_strong_public_password(password):
            _s.log_security_event("public_register", request, "weak_password", email=email_normalized)
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/register", msg="weak_password", next=safe_next),
                status_code=303,
            )

        user, status_label = _s.upsert_public_user_for_register(
            db=db,
            models_module=_s.models,
            existing_user=exists,
            full_name=full_name_normalized,
            email=email_normalized,
            phone=phone_normalized,
            password_hash=_s.hash_password(password),
            email_verified=not _s._is_email_verification_required(),
            now=_s.utcnow_naive(),
        )
        _s._ensure_client_for_public_register(db, user, safe_next)
        db.commit()
        db.refresh(user)

        queued, mail_info = (True, "verification_bypassed")
        if _s._is_email_verification_required():
            queued, mail_info = _s.queue_verify_email_for_user(request, user, next_url=safe_next)
        if not queued:
            _s.log_security_event(
                "public_register",
                request,
                "mail_failed",
                email=user.email,
                details={"mail_error": mail_info[:200], "state": status_label},
            )
        else:
            _s.log_security_event(
                "public_register",
                request,
                "success",
                email=user.email,
                details={"mail_status": "queued", "state": status_label},
            )
        token = _s.create_public_access_token(user.id)
        response = _s.RedirectResponse(
            url=_s.build_post_register_redirect_url(
                safe_next=safe_next,
                verification_required=_s._is_email_verification_required(),
                queued=queued,
                mail_info=mail_info,
                url_with_params_fn=_s._url_with_params,
                mail_fail_why_token_fn=_s.public_mail_fail_why_token,
            ),
            status_code=303,
        )
        _s.set_public_auth_cookie(
            response=response,
            cookie_name=_s.PUBLIC_COOKIE_NAME,
            token=token,
            secure=_s._cookie_secure_flag(request),
        )
        return response

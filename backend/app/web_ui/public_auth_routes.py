"""Public account: register, login, profile, verification, password reset."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_public_auth_routes(router: APIRouter) -> None:
    """Register, login, account, verify, forgot/reset password."""

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
    
    
    @router.get("/public/login", response_class=_s.HTMLResponse)
    def public_login_page(request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH):
        return _s.templates.TemplateResponse(request, "public_login.html", {"next": next, **_s._analytics_context("public_login")})
    
    
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
    def public_logout():
        # _s.Request object is not required for logout, so this event is not logged here.
        response = _s.RedirectResponse(url=f"{_s.PUBLIC_INDEX_DEFAULT_PATH}&msg=logged_out", status_code=303)
        response.delete_cookie(_s.PUBLIC_COOKIE_NAME)
        return response
    
    
    @router.get("/public/account", response_class=_s.HTMLResponse)
    def public_account_page(request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH, db: _s.Session = _s.Depends(_s.get_db)):
        safe_next = _s._sanitize_next_url(request.query_params.get("next") or next)
        user = _s._current_public_user(request, db)
        if not user:
            return _s._public_login_redirect(next_url=safe_next)
        cc, phone_local = _s.public_account_phone_prefill(user)
        try:
            center_id_loyalty = int(_s.public_center_id_str_from_next(safe_next))
        except ValueError:
            center_id_loyalty = 1
        center_loyalty = db.get(_s.models.Center, center_id_loyalty)
        loyalty_ctx = _s.build_public_loyalty_context(db, center_id_loyalty, user, center=center_loyalty)
        return _s.templates.TemplateResponse(
            request,
            "public_account.html",
            {
                "next": safe_next,
                "user": user,
                "country_code": cc,
                "phone_local": phone_local,
                "loyalty_program_rows": _s.loyalty_program_table_rows(center_loyalty),
                **loyalty_ctx,
                **_s._analytics_context("public_account"),
            },
        )
    
    
    @router.post("/public/account")
    def public_account_update(
        request: _s.Request,
        full_name: str = _s.Form(...),
        country_code: str = _s.Form(...),
        phone: str = _s.Form(...),
        next: str = _s.Form(_s.PUBLIC_INDEX_DEFAULT_PATH),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        safe_next = _s._sanitize_next_url(next)
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(next_url=safe_next, msg="ip_blocked")
        user = _s._current_public_user(request, db)
        if not user:
            return _s._public_login_redirect(next_url=safe_next)
        full_name_n = full_name.strip()
        if not full_name_n or not phone.strip() or not country_code.strip():
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/account", msg="required_fields", next=safe_next),
                status_code=303,
            )
        phone_n = _s._normalize_phone_with_country(country_code, phone)
        if phone_n is None:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/account", msg="invalid_phone", next=safe_next),
                status_code=303,
            )
        other = (
            db.query(_s.models.PublicUser)
            .filter(
                _s.models.PublicUser.phone == phone_n,
                _s.models.PublicUser.is_deleted.is_(False),
                _s.models.PublicUser.id != user.id,
            )
            .first()
        )
        if other:
            _s.log_security_event(
                "public_account_update",
                request,
                "phone_conflict",
                email=user.email,
                details={"public_user_id": user.id},
            )
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/account", msg="phone_exists", next=safe_next),
                status_code=303,
            )
        user.full_name = full_name_n
        user.phone = phone_n
        db.commit()
        _s.log_security_event(
            "public_account_update",
            request,
            "success",
            email=user.email,
            details={"public_user_id": user.id},
        )
        return _s.RedirectResponse(
            url=_s._url_with_params("/public/account", msg="saved", next=safe_next),
            status_code=303,
        )
    
    
    @router.post("/public/account/delete/request")
    def public_account_delete_request(
        request: _s.Request,
        next: str = _s.Form(_s.PUBLIC_INDEX_DEFAULT_PATH),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        safe_next = _s._sanitize_next_url(next)
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(next_url=safe_next, msg="ip_blocked")
        user = _s._current_public_user(request, db)
        if not user:
            return _s._public_login_redirect(next_url=safe_next)
        if _s.is_public_account_delete_request_rate_limited(
            request=request,
            email=user.email,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            log_security_event_fn=_s.log_security_event,
        ):
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/account", msg="delete_rate_limited", next=safe_next),
                status_code=303,
            )
        confirm_url = _s.build_account_delete_confirm_url(request, user, safe_next)
        queued, mail_info = _s.queue_account_delete_confirmation_email(user.email, confirm_url, full_name=user.full_name)
        if not queued:
            _s.log_security_event(
                "public_account_delete_request",
                request,
                "mail_failed",
                email=user.email,
                details={"mail_error": mail_info[:200]},
            )
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/account", msg="delete_mail_failed", next=safe_next),
                status_code=303,
            )
        _s.log_security_event(
            "public_account_delete_request",
            request,
            "success",
            email=user.email,
            details={"mail_status": "sent"},
        )
        return _s.RedirectResponse(
            url=_s._url_with_params("/public/account", msg="delete_mail_sent", next=safe_next),
            status_code=303,
        )
    
    
    @router.get("/public/account/delete/confirm")
    def public_account_delete_confirm(
        request: _s.Request,
        token: str = "",
        next: str = _s.PUBLIC_INDEX_DEFAULT_PATH,
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        token_value = _s.sanitize_public_token(token)
        safe_next = _s._sanitize_next_url(next)
        user, err_msg = _s.resolve_public_account_delete_confirmation(
            token_value=token_value,
            db=db,
            decode_token_fn=_s.decode_public_account_delete_token,
            models_module=_s.models,
        )
        if err_msg:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/account", msg=err_msg, next=safe_next),
                status_code=303,
            )
        _s._soft_delete_public_user(user)
        db.commit()
        _s.log_security_event(
            "public_account_delete_confirm",
            request,
            "success",
            email=user.email,
            details={"public_user_id": user.id},
        )
        response = _s.RedirectResponse(url=_s.public_index_url_from_next(safe_next, msg="account_deleted"), status_code=303)
        response.delete_cookie(_s.PUBLIC_COOKIE_NAME)
        return response
    
    
    @router.get("/public/verify-pending", response_class=_s.HTMLResponse)
    def public_verify_pending(request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH, db: _s.Session = _s.Depends(_s.get_db)):
        safe_next = _s._sanitize_next_url(next)
        msg_param = (request.query_params.get("msg") or "").strip()
        vk_param = (request.query_params.get("vk") or "").strip()
        flash_user = _s.public_user_from_verify_flash_token(db, vk_param) if msg_param == "email_verified" else None
        user = _s._current_public_user(request, db)
        if msg_param == "email_verified":
            target: _s.models.PublicUser | None = None
            if flash_user:
                target = flash_user
            elif user and user.email_verified:
                target = user
            if target:
                index_url = _s.public_index_url_from_next(safe_next, msg="email_verified")
                fn = (target.full_name or "").strip().split()
                user_first_name = fn[0] if fn else ""
                response = _s.templates.TemplateResponse(
                    request,
                    "public_verify_pending.html",
                    {
                        "next": safe_next,
                        "user": target,
                        "show_dev_verify_link": False,
                        "dev_verify_url": "",
                        "show_email_verified_success": True,
                        "index_url": index_url,
                        "user_first_name": user_first_name,
                        **_s._analytics_context("public_verify_pending"),
                    },
                )
                if (not user) or user.id != target.id:
                    _s.set_public_auth_cookie(
                        response=response,
                        cookie_name=_s.PUBLIC_COOKIE_NAME,
                        token=_s.create_public_access_token(target.id),
                        secure=_s._cookie_secure_flag(request),
                    )
                return response
        if not user:
            return _s._public_login_redirect(next_url=safe_next)
        if not _s._is_email_verification_required():
            return _s.RedirectResponse(url=_s.public_index_url_from_next(safe_next), status_code=303)
        if user.email_verified:
            return _s.RedirectResponse(url=_s.public_index_url_from_next(safe_next), status_code=303)
        show_dev_verify_link = _s._is_truthy_env(_s.os.getenv("SHOW_DEV_VERIFY_LINK"))
        dev_verify_url = _s.build_verify_url(request, user, next_url=safe_next) if show_dev_verify_link else ""
        return _s.templates.TemplateResponse(
            request,
            "public_verify_pending.html",
            {
                "next": safe_next,
                "user": user,
                "show_dev_verify_link": show_dev_verify_link,
                "dev_verify_url": dev_verify_url,
                "show_email_verified_success": False,
                **_s._analytics_context("public_verify_pending"),
            },
        )
    
    
    @router.post("/public/resend-verification")
    def public_resend_verification(
        request: _s.Request,
        next: str = _s.Form(_s.PUBLIC_INDEX_DEFAULT_PATH),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        safe_next = _s._sanitize_next_url(next)
        if _s._is_ip_blocked(db, request):
            return _s._public_login_redirect(next_url=safe_next, msg="ip_blocked")
        if _s.is_public_resend_verification_rate_limited(
            request=request,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            log_security_event_fn=_s.log_security_event,
        ):
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", msg="rate_limited", next=safe_next),
                status_code=303,
            )
        user = _s._current_public_user(request, db)
        if not user:
            return _s._public_login_redirect(next_url=safe_next)
        now = _s.utcnow_naive()
        if user.verification_sent_at and (now - user.verification_sent_at).total_seconds() < 60:
            _s.log_security_event("public_resend_verification", request, "too_soon", email=user.email)
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", msg="resend_too_soon", next=safe_next),
                status_code=303,
            )
        user.verification_sent_at = now
        db.commit()
        queued, mail_info = _s.queue_verify_email_for_user(request, user, next_url=safe_next)
        if not queued:
            _s.log_security_event(
                "public_resend_verification",
                request,
                "mail_failed",
                email=user.email,
                details={"mail_error": mail_info[:200]},
            )
            why = _s.public_mail_fail_why_token(mail_info)
            vp = {"msg": "mail_failed", "next": safe_next}
            if why:
                vp["why"] = why
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", **vp),
                status_code=303,
            )
        _s.log_security_event(
            "public_resend_verification",
            request,
            "success",
            email=user.email,
            details={"mail_status": "queued"},
        )
        return _s.RedirectResponse(
            url=_s._url_with_params("/public/verify-pending", msg="resent", next=safe_next),
            status_code=303,
        )
    
    
    @router.get("/public/verify-email")
    def public_verify_email(
        request: _s.Request,
        token: str = "",
        next: str = _s.PUBLIC_INDEX_DEFAULT_PATH,
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        token_value = _s.sanitize_public_token(token)
        safe_next = _s._sanitize_next_url(next)
        user, err_msg = _s.resolve_public_email_verification(
            token_value=token_value,
            db=db,
            decode_token_fn=_s.decode_public_email_verification_token,
            models_module=_s.models,
        )
        if err_msg:
            return _s.RedirectResponse(
                url=_s._url_with_params("/public/verify-pending", msg=err_msg, next=safe_next),
                status_code=303,
            )
        if not user.email_verified:
            user.email_verified = True
            db.commit()
        session_token = _s.create_public_access_token(user.id)
        flash_token = _s.create_public_email_verify_flash_token(user.id, user.email)
        response = _s.RedirectResponse(
            url=_s._url_with_params("/public/verify-pending", msg="email_verified", next=safe_next, vk=flash_token),
            status_code=303,
        )
        _s.set_public_auth_cookie(
            response=response,
            cookie_name=_s.PUBLIC_COOKIE_NAME,
            token=session_token,
            secure=_s._cookie_secure_flag(request),
        )
        _s.log_security_event(
            "public_verify_email",
            request,
            "success",
            email=user.email,
            details={"public_user_id": user.id},
        )
        return response
    
    
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
    

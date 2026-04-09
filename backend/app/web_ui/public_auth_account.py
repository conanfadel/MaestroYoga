"""Account profile update and soft-delete confirmation routes."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_public_auth_account_routes(router: APIRouter) -> None:
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
    
    


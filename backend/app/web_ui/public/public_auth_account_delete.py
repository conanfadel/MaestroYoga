"""Public account soft-delete: email request and token confirm."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_account_delete_routes(router: APIRouter) -> None:
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

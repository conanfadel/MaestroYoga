"""Resend verification email and verify-email token link."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_verify_actions_routes(router: APIRouter) -> None:
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

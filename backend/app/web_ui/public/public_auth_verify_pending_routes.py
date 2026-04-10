"""Public email verification pending page (GET)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_verify_pending_routes(router: APIRouter) -> None:
    @router.get("/public/verify-pending", response_class=_s.HTMLResponse)
    def public_verify_pending(
        request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH, db: _s.Session = _s.Depends(_s.get_db)
    ):
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

"""Public account page (GET) and profile update (POST)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_auth_account_profile_routes(router: APIRouter) -> None:
    @router.get("/public/account", response_class=_s.HTMLResponse)
    def public_account_page(
        request: _s.Request, next: str = _s.PUBLIC_INDEX_DEFAULT_PATH, db: _s.Session = _s.Depends(_s.get_db)
    ):
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

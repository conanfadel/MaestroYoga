def upsert_public_user_for_register(
    *,
    db,
    models_module,
    existing_user,
    full_name: str,
    email: str,
    phone: str,
    password_hash: str,
    email_verified: bool,
    now,
):
    if existing_user and existing_user.is_deleted:
        user = existing_user
        user.full_name = full_name
        user.email = email
        user.phone = phone
        user.password_hash = password_hash
        user.email_verified = email_verified
        user.verification_sent_at = now
        user.is_active = True
        user.is_deleted = False
        user.deleted_at = None
        return user, "restored"

    user = models_module.PublicUser(
        full_name=full_name,
        email=email,
        phone=phone,
        password_hash=password_hash,
        email_verified=email_verified,
        verification_sent_at=now,
        is_active=True,
        is_deleted=False,
    )
    db.add(user)
    return user, "created"


def build_post_register_redirect_url(
    *,
    safe_next: str,
    verification_required: bool,
    queued: bool,
    mail_info: str,
    url_with_params_fn,
    mail_fail_why_token_fn,
) -> str:
    if verification_required:
        next_msg = "registered" if queued else "mail_failed"
        vp_params: dict[str, str] = {"msg": next_msg, "next": safe_next}
        if not queued:
            why = mail_fail_why_token_fn(mail_info)
            if why:
                vp_params["why"] = why
        return url_with_params_fn("/public/verify-pending", **vp_params)

    sep = "&" if "?" in safe_next else "?"
    return f"{safe_next}{sep}msg=registered_no_verify"


def build_post_login_redirect_url(
    *,
    safe_next: str,
    verification_required: bool,
    email_verified: bool,
    url_with_params_fn,
) -> str:
    if verification_required and not email_verified:
        return url_with_params_fn("/public/verify-pending", next=safe_next)
    return safe_next


def is_public_register_rate_limited(
    *,
    request,
    email: str,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    register_key = request_key_fn(request, "public_register", email)
    allowed = allow_fn(
        register_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_register", request, "rate_limited", email=email)
    return True


def is_public_login_rate_limited(
    *,
    request,
    email: str,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    login_key = request_key_fn(request, "public_login", email)
    allowed = allow_fn(
        login_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_login", request, "rate_limited", email=email)
    return True


def set_public_auth_cookie(
    *,
    response,
    cookie_name: str,
    token: str,
    secure: bool,
) -> None:
    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=60 * 60 * 24 * 7,
    )

def is_public_account_delete_request_rate_limited(
    *,
    request,
    email: str,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    delete_key = request_key_fn(request, "public_account_delete_request", email.lower())
    allowed = allow_fn(
        delete_key,
        limit=3,
        window_seconds=600,
        lockout_seconds=900,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_account_delete_request", request, "rate_limited", email=email)
    return True


def sanitize_public_token(token: str) -> str:
    return (token or "").strip().strip("<>").strip('"').strip("'")


def is_public_resend_verification_rate_limited(
    *,
    request,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    resend_key = request_key_fn(request, "public_resend_verify")
    allowed = allow_fn(
        resend_key,
        limit=6,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_resend_verification", request, "rate_limited")
    return True


def is_public_forgot_password_rate_limited(
    *,
    request,
    email: str,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    forgot_key = request_key_fn(request, "public_forgot_password", email)
    allowed = allow_fn(
        forgot_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_forgot_password", request, "rate_limited", email=email)
    return True


def is_public_reset_password_rate_limited(
    *,
    request,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    reset_key = request_key_fn(request, "public_reset_password")
    allowed = allow_fn(
        reset_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_reset_password", request, "rate_limited")
    return True


def reset_password_validation_error(
    *,
    password: str,
    confirm_password: str,
    is_strong_password_fn,
) -> str | None:
    if not is_strong_password_fn(password):
        return "weak_password"
    if password != confirm_password:
        return "password_mismatch"
    return None


def resolve_public_account_delete_confirmation(
    *,
    token_value: str,
    db,
    decode_token_fn,
    models_module,
) -> tuple[object | None, str]:
    if not token_value:
        return None, "delete_invalid_link"
    try:
        payload = decode_token_fn(token_value)
        user_id = int(payload.get("sub"))
    except Exception:
        return None, "delete_invalid_link"
    token_email = str(payload.get("email", "")).strip().lower()
    user = db.get(models_module.PublicUser, user_id)
    if not user or user.is_deleted or user.email.lower().strip() != token_email:
        return None, "delete_invalid_link"
    return user, ""


def resolve_public_email_verification(
    *,
    token_value: str,
    db,
    decode_token_fn,
    models_module,
) -> tuple[object | None, str]:
    if not token_value:
        return None, "invalid_link"
    try:
        payload = decode_token_fn(token_value)
    except Exception:
        return None, "expired_link"
    try:
        user_id = int(payload.get("sub"))
    except Exception:
        return None, "invalid_link"
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models_module.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        return None, "invalid_link"
    return user, ""

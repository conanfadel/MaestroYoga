import os
from html import escape as html_escape


def is_valid_feedback_message(message: str, *, min_len: int = 3, max_len: int = 8000) -> bool:
    text = (message or "").strip()
    return min_len <= len(text) <= max_len


def is_valid_feedback_contact_name(name: str, *, min_len: int = 2, max_len: int = 200) -> bool:
    text = (name or "").strip()
    return min_len <= len(text) <= max_len


def is_valid_feedback_email(email: str, *, max_len: int = 254) -> bool:
    text = (email or "").strip().lower()
    return bool(text) and "@" in text and len(text) <= max_len


async def build_feedback_attachments(
    uploads,
    *,
    allowed_types: set[str] | frozenset[str],
    max_image_bytes: int,
    max_images: int,
) -> tuple[list[tuple[str, bytes, str]], str | None]:
    attachments: list[tuple[str, bytes, str]] = []
    upload_list = uploads if uploads else []
    for uf in upload_list:
        if not uf.filename:
            continue
        ct = (uf.content_type or "").split(";")[0].strip().lower()
        if ct not in allowed_types:
            return [], "feedback_bad_image"
        raw = await uf.read()
        if len(raw) > max_image_bytes:
            return [], "feedback_image_too_large"
        if len(attachments) >= max_images:
            break
        safe_name = os.path.basename(uf.filename or "image.jpg")[:180]
        attachments.append((safe_name, raw, ct))
    return attachments, None


def build_feedback_email_payload(
    *,
    app_name: str,
    center_name: str,
    center_id: int,
    cat_label: str,
    contact_name: str,
    contact_phone: str,
    contact_email: str,
    message: str,
    ip: str,
) -> tuple[str, str, str]:
    subject = f"{app_name} — {center_name} — {cat_label}"
    body_lines = [
        f"المركز: {center_name} (center_id={center_id})",
        f"التصنيف: {cat_label}",
        f"الاسم: {contact_name}",
        f"الجوال: {contact_phone or '—'}",
        f"البريد (من حساب المستخدم): {contact_email}",
        "",
        "النص:",
        message,
        "",
        f"عنوان IP: {ip}",
    ]
    body = "\n".join(body_lines)
    html_body = (
        f"<div dir='rtl' style='font-family:Tahoma,Arial,sans-serif;line-height:1.6'>"
        f"<p><strong>المركز:</strong> {html_escape(center_name)}</p>"
        f"<p><strong>التصنيف:</strong> {html_escape(cat_label)}</p>"
        f"<p><strong>الاسم:</strong> {html_escape(contact_name)}</p>"
        f"<p><strong>الجوال:</strong> {html_escape(contact_phone or '—')}</p>"
        f"<p><strong>البريد:</strong> {html_escape(contact_email)}</p>"
        f"<p><strong>النص:</strong></p><pre style='white-space:pre-wrap'>{html_escape(message)}</pre>"
        f"<p><strong>IP:</strong> {html_escape(ip)}</p>"
        f"</div>"
    )
    return subject, body, html_body


def is_feedback_rate_limited(
    *,
    request,
    center_id: int,
    email: str | None,
    request_key_fn,
    allow_fn,
    max_lockout_seconds: int,
    log_security_event_fn,
) -> bool:
    fb_key = request_key_fn(request, "public_feedback", f"{center_id}")
    allowed = allow_fn(
        fb_key,
        limit=5,
        window_seconds=3600,
        lockout_seconds=120,
        max_lockout_seconds=max_lockout_seconds,
    )
    if allowed:
        return False
    log_security_event_fn("public_feedback", request, "rate_limited", email=email or None)
    return True


def feedback_send_result_message(
    *,
    sent_ok: bool,
    send_reason: str,
    request,
    email: str | None,
    log_security_event_fn,
) -> str:
    if sent_ok:
        log_security_event_fn("public_feedback", request, "success", email=email or None)
        return "feedback_sent"
    log_security_event_fn(
        "public_feedback",
        request,
        "send_failed",
        email=email or None,
        details={"reason": (send_reason or "")[:400]},
    )
    return "feedback_error"


def validate_feedback_input_fields(
    *,
    message: str,
    contact_name: str,
    contact_phone: str,
    account_email: str,
    is_valid_message_fn,
    is_valid_contact_name_fn,
    is_valid_email_fn,
) -> tuple[str, str, str, str, str | None]:
    msg_text = (message or "").strip()
    if not is_valid_message_fn(msg_text):
        return "", "", "", "", "feedback_error"

    name_sub = (contact_name or "").strip()
    if not is_valid_contact_name_fn(name_sub):
        return "", "", "", "", "feedback_error"

    phone_sub = (contact_phone or "").strip()[:40]
    ce = (account_email or "").strip().lower()
    if not is_valid_email_fn(ce):
        return "", "", "", "", "feedback_error"

    return msg_text, name_sub, phone_sub, ce, None


def resolve_feedback_category(
    *,
    category: str,
    category_labels: dict[str, str],
) -> tuple[str, str | None, str | None]:
    cat_key = (category or "").strip().lower()
    if cat_key not in category_labels:
        return "", None, "feedback_error"
    return cat_key, category_labels[cat_key], None


async def prepare_feedback_submission(
    *,
    request,
    center_id: int,
    center_name: str,
    category: str,
    message: str,
    contact_name: str,
    contact_phone: str,
    account_email: str,
    images,
    category_labels: dict[str, str],
    allowed_image_types: set[str] | frozenset[str],
    max_image_bytes: int,
    max_images: int,
    max_lockout_seconds: int,
    request_key_fn,
    allow_fn,
    log_security_event_fn,
    client_ip_fn,
    app_name: str,
    is_valid_message_fn,
    is_valid_contact_name_fn,
    is_valid_email_fn,
) -> tuple[dict | None, str | None]:
    cat_key, cat_label, category_error = resolve_feedback_category(
        category=category,
        category_labels=category_labels,
    )
    if category_error:
        return None, category_error

    msg_text, name_sub, phone_sub, ce, input_error = validate_feedback_input_fields(
        message=message,
        contact_name=contact_name,
        contact_phone=contact_phone,
        account_email=account_email,
        is_valid_message_fn=is_valid_message_fn,
        is_valid_contact_name_fn=is_valid_contact_name_fn,
        is_valid_email_fn=is_valid_email_fn,
    )
    if input_error:
        return None, input_error

    if is_feedback_rate_limited(
        request=request,
        center_id=center_id,
        email=ce,
        request_key_fn=request_key_fn,
        allow_fn=allow_fn,
        max_lockout_seconds=max_lockout_seconds,
        log_security_event_fn=log_security_event_fn,
    ):
        return None, "feedback_rate_limited"

    attachments, attachments_error = await build_feedback_attachments(
        images,
        allowed_types=allowed_image_types,
        max_image_bytes=max_image_bytes,
        max_images=max_images,
    )
    if attachments_error:
        return None, attachments_error

    ip = client_ip_fn(request)
    subject, body, html_body = build_feedback_email_payload(
        app_name=app_name,
        center_name=center_name,
        center_id=center_id,
        cat_label=cat_label or "",
        contact_name=name_sub,
        contact_phone=phone_sub,
        contact_email=ce,
        message=msg_text,
        ip=ip,
    )
    return {
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "attachments": attachments,
        "email": ce,
    }, None

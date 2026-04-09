"""Validation, async executor, and queue wrappers for transactional sends."""

from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor

from ._env import MAILER_ASYNC_WORKERS, _looks_like_placeholder, _mailer_delivery_mode, _relay_endpoint
from ._transactional import (
    send_account_delete_confirmation_email,
    send_email_verification_email,
    send_password_reset_email,
)

_MAILER_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, MAILER_ASYNC_WORKERS))


def _log_mail_future(prefix: str, fut: Future[tuple[bool, str]]) -> None:
    try:
        ok, info = fut.result()
        if not ok:
            print(f"[MAILER][ERROR] {prefix} failed asynchronously: {info}")
    except Exception as exc:
        print(f"[MAILER][ERROR] {prefix} crashed asynchronously: {exc}")


def validate_mailer_settings() -> tuple[bool, str]:
    mail_provider = os.getenv("MAIL_PROVIDER", "smtp").strip().lower()
    if mail_provider in {"http_relay", "apps_script"}:
        if not _relay_endpoint():
            return False, "missing_mail_relay_url"
        if _looks_like_placeholder(os.getenv("MAIL_RELAY_TOKEN", "").strip()):
            return False, "invalid_mail_relay_token_placeholder"
        return True, "ok"

    if mail_provider == "resend":
        key = os.getenv("RESEND_API_KEY", "").strip()
        if not key:
            return False, "missing_resend_api_key"
        if _looks_like_placeholder(key):
            return False, "invalid_resend_api_key_placeholder"
        from_addr = os.getenv("RESEND_FROM", os.getenv("SMTP_FROM", "")).strip()
        if not from_addr:
            return False, "missing_resend_from"
        return True, "ok"

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    if not smtp_host:
        return False, "missing_smtp_host"
    if not smtp_user:
        return False, "missing_smtp_user"
    if not smtp_password:
        return False, "missing_smtp_password"
    if _looks_like_placeholder(smtp_password):
        return False, "invalid_smtp_password_placeholder"
    return True, "ok"


def queue_email_verification_email(to_email: str, verification_url: str, full_name: str = "") -> tuple[bool, str]:
    ok, reason = validate_mailer_settings()
    if not ok:
        print(f"[MAILER][CONFIG] email_verification blocked: {reason}")
        return False, reason
    if _mailer_delivery_mode() == "sync":
        sent_ok, sent_reason = send_email_verification_email(to_email, verification_url, full_name)
        if not sent_ok:
            print(f"[MAILER][ERROR] email_verification send failed: {sent_reason}")
        return sent_ok, sent_reason
    fut = _MAILER_EXECUTOR.submit(send_email_verification_email, to_email, verification_url, full_name)
    fut.add_done_callback(lambda done: _log_mail_future("email_verification", done))
    return True, "queued"


def queue_password_reset_email(to_email: str, reset_url: str, full_name: str = "") -> tuple[bool, str]:
    ok, reason = validate_mailer_settings()
    if not ok:
        print(f"[MAILER][CONFIG] password_reset blocked: {reason}")
        return False, reason
    # دائمًا متزامن: حتى لا يُعرض «تم الإرسال» ثم يفشل الإرسال في الخلفية دون إبلاغ المستخدم.
    sent_ok, sent_reason = send_password_reset_email(to_email, reset_url, full_name)
    if not sent_ok:
        print(f"[MAILER][ERROR] password_reset send failed: {sent_reason}")
    return sent_ok, sent_reason


def queue_account_delete_confirmation_email(to_email: str, confirm_url: str, full_name: str = "") -> tuple[bool, str]:
    ok, reason = validate_mailer_settings()
    if not ok:
        print(f"[MAILER][CONFIG] account_delete blocked: {reason}")
        return False, reason
    # متزامن لإرجاع حالة دقيقة للمستخدم مباشرة.
    sent_ok, sent_reason = send_account_delete_confirmation_email(to_email, confirm_url, full_name)
    if not sent_ok:
        print(f"[MAILER][ERROR] account_delete send failed: {sent_reason}")
    return sent_ok, sent_reason

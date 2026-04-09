"""HTTP mail relay and Resend API transports."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from ._env import _looks_like_placeholder, _relay_endpoint


def _send_via_http_relay(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None,
) -> tuple[bool, str]:
    relay_url = _relay_endpoint()
    relay_token = os.getenv("MAIL_RELAY_TOKEN", "").strip()
    if not relay_url:
        return False, "missing_mail_relay_url"
    if not relay_token:
        return False, "missing_mail_relay_token"
    payload = {
        "token": relay_token,
        "to": to_email,
        "subject": subject,
        "text": body,
        "html": html_body or "",
        "from": os.getenv("SMTP_FROM", "").strip(),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        relay_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "MaestroYoga-Mailer/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = int(getattr(response, "status", 200))
            body_bytes = response.read() or b""
            body_text = body_bytes.decode("utf-8", errors="ignore").strip()
            if 200 <= status < 300:
                return True, "ok"
            return False, f"relay_http_{status}:{body_text[:200]}"
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore").strip()
        return False, f"relay_http_{exc.code}:{err_body[:200]}"
    except Exception as exc:
        return False, f"relay_error:{exc}"


def _maybe_log_resend_sandbox_restriction(reason: str) -> None:
    low = reason.lower()
    if "resend_http_403" not in low:
        return
    if not (
        "testing emails" in low or "verify a domain" in low or "validation_error" in low
    ):
        return
    print(
        "[MAILER][HINT] Resend (وضع اختبار): الإرسال مسموح فقط إلى بريد مالك حساب Resend. "
        "للإنتاج: تحقّق من نطاقك في https://resend.com/domains واستخدم RESEND_FROM (وSMTP_FROM) ببريد من ذلك النطاق. "
        "للتجربة فقط (غير آمن للإنتاج): PUBLIC_REQUIRE_EMAIL_VERIFICATION=0 يعطّل طلب تأكيد البريد."
    )


def _send_via_resend(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None,
) -> tuple[bool, str]:
    """إرسال عبر Resend API (HTTPS :443) — مناسب لـ Render حيث غالبًا يُحجب SMTP الصادر."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_addr = os.getenv("RESEND_FROM", os.getenv("SMTP_FROM", "")).strip()
    if not api_key:
        return False, "missing_resend_api_key"
    if _looks_like_placeholder(api_key):
        return False, "invalid_resend_api_key_placeholder"
    if not from_addr:
        return False, "missing_resend_from"
    payload: dict[str, object] = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if html_body:
        payload["html"] = html_body
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MaestroYoga-Mailer/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            status = int(getattr(response, "status", 200))
            raw = (response.read() or b"").decode("utf-8", errors="ignore").strip()
            if 200 <= status < 300:
                return True, "ok"
            reason = f"resend_http_{status}:{raw[:300]}"
            _maybe_log_resend_sandbox_restriction(reason)
            return False, reason
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore").strip()
        reason = f"resend_http_{exc.code}:{err_body[:300]}"
        _maybe_log_resend_sandbox_restriction(reason)
        return False, reason
    except Exception as exc:
        return False, f"resend_error:{exc}"


def _send_via_resend_with_attachments(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None,
    attachments: list[tuple[str, bytes, str]],
) -> tuple[bool, str]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_addr = os.getenv("RESEND_FROM", os.getenv("SMTP_FROM", "")).strip()
    if not api_key:
        return False, "missing_resend_api_key"
    if _looks_like_placeholder(api_key):
        return False, "invalid_resend_api_key_placeholder"
    if not from_addr:
        return False, "missing_resend_from"
    payload: dict[str, object] = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": body,
        "attachments": [
            {"filename": fn, "content": base64.b64encode(raw).decode("ascii")}
            for fn, raw, _ct in attachments
        ],
    }
    if html_body:
        payload["html"] = html_body
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MaestroYoga-Mailer/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status = int(getattr(response, "status", 200))
            raw = (response.read() or b"").decode("utf-8", errors="ignore").strip()
            if 200 <= status < 300:
                return True, "ok"
            reason = f"resend_http_{status}:{raw[:300]}"
            _maybe_log_resend_sandbox_restriction(reason)
            return False, reason
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore").strip()
        reason = f"resend_http_{exc.code}:{err_body[:300]}"
        _maybe_log_resend_sandbox_restriction(reason)
        return False, reason
    except Exception as exc:
        return False, f"resend_error:{exc}"

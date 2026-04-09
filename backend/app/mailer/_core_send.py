"""Primary send path: SMTP, Resend, relay, pywhatkit; optional attachments."""

from __future__ import annotations

import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import pywhatkit  # type: ignore
except Exception:
    pywhatkit = None

from ._env import _looks_like_placeholder, _parse_smtp_port, _smtp_transport_mode
from ._remote_api import _send_via_http_relay, _send_via_resend, _send_via_resend_with_attachments
from ._smtp_transport import _build_smtp_attempts, _send_smtp_message


def _send_mail(to_email: str, subject: str, body: str, html_body: str | None = None) -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = _parse_smtp_port(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "no-reply@maestroyoga.local")
    mail_provider = os.getenv("MAIL_PROVIDER", "smtp").strip().lower()
    smtp_security = _smtp_transport_mode()

    try:
        if mail_provider in {"http_relay", "apps_script"}:
            return _send_via_http_relay(to_email=to_email, subject=subject, body=body, html_body=html_body)

        if mail_provider == "resend":
            return _send_via_resend(to_email=to_email, subject=subject, body=body, html_body=html_body)

        if not smtp_host:
            return False, "missing_smtp_host"
        if _looks_like_placeholder(smtp_password):
            return False, "invalid_smtp_password_placeholder"
        if not smtp_user:
            return False, "missing_smtp_user"

        if mail_provider == "pywhatkit":
            if pywhatkit is None:
                raise RuntimeError("pywhatkit is not installed")
            if not smtp_password:
                raise RuntimeError("SMTP_PASSWORD is required for pywhatkit")
            pywhatkit.send_mail(
                to_email,
                subject,
                body,
                smtp_user,
                smtp_password,
            )
            return True, "ok"

        if html_body:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email
            msg.attach(MIMEText(body, "plain", _charset="utf-8"))
            msg.attach(MIMEText(html_body, "html", _charset="utf-8"))
        else:
            msg = MIMEText(body, _charset="utf-8")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email

        msg_raw = msg.as_string()
        last_error = "unknown"
        for mode, port in _build_smtp_attempts(smtp_host, smtp_port, smtp_security):
            try:
                _send_smtp_message(
                    smtp_host=smtp_host,
                    smtp_port=port,
                    smtp_security=mode,
                    smtp_user=smtp_user,
                    smtp_password=smtp_password,
                    smtp_from=smtp_from,
                    to_email=to_email,
                    msg_raw=msg_raw,
                )
                if (mode, port) != (smtp_security, smtp_port):
                    print(
                        "[MAILER][WARN] Primary SMTP transport failed; "
                        f"succeeded via fallback mode={mode} port={port}"
                    )
                return True, "ok"
            except Exception as exc:
                last_error = f"mode={mode} port={port} error={exc}"
        raise RuntimeError(last_error)
    except Exception as exc:
        err_text = str(exc).lower()
        print(f"[MAILER][ERROR] Failed to send email to {to_email}: {exc}")
        if "unreachable" in err_text or "network is unreachable" in err_text or "[errno 101]" in err_text:
            print(
                "[MAILER][HINT] منصات مثل Render غالبًا تحجب SMTP. عيّن MAIL_PROVIDER=resend وRESEND_API_KEY (HTTPS)."
            )
        return False, str(exc)


def feedback_destination_email() -> str:
    v = os.getenv("FEEDBACK_TO_EMAIL", "").strip()
    if v:
        return v
    return os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")).strip()


def send_mail_with_attachments(
    to_email: str,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> tuple[bool, str]:
    """إرسال بريد مع مرفقات (صور وغيرها). يدعم SMTP و Resend؛ المزودات الأخرى تُرفض عند وجود مرفقات."""
    attachments = attachments or []
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = _parse_smtp_port(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "no-reply@maestroyoga.local")
    mail_provider = os.getenv("MAIL_PROVIDER", "smtp").strip().lower()
    smtp_security = _smtp_transport_mode()

    try:
        if mail_provider in {"http_relay", "apps_script"}:
            if attachments:
                return False, "attachments_not_supported_for_relay"
            return _send_mail(to_email, subject, body, html_body)

        if mail_provider == "resend":
            if not attachments:
                return _send_via_resend(to_email=to_email, subject=subject, body=body, html_body=html_body)
            return _send_via_resend_with_attachments(
                to_email=to_email,
                subject=subject,
                body=body,
                html_body=html_body,
                attachments=attachments,
            )

        if not smtp_host:
            return False, "missing_smtp_host"
        if _looks_like_placeholder(smtp_password):
            return False, "invalid_smtp_password_placeholder"
        if not smtp_user:
            return False, "missing_smtp_user"

        if mail_provider == "pywhatkit":
            if attachments:
                return False, "attachments_not_supported_for_pywhatkit"
            return _send_mail(to_email, subject, body, html_body)

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_email
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain", _charset="utf-8"))
        if html_body:
            alt.attach(MIMEText(html_body, "html", _charset="utf-8"))
        msg.attach(alt)

        for filename, data, ctype in attachments:
            maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
            maintype = maintype or "application"
            subtype = subtype or "octet-stream"
            if maintype == "image":
                part = MIMEImage(data, _subtype=subtype)
            else:
                part = MIMEBase(maintype, subtype)
                part.set_payload(data)
                encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        msg_raw = msg.as_string()
        last_error = "unknown"
        for mode, port in _build_smtp_attempts(smtp_host, smtp_port, smtp_security):
            try:
                _send_smtp_message(
                    smtp_host=smtp_host,
                    smtp_port=port,
                    smtp_security=mode,
                    smtp_user=smtp_user,
                    smtp_password=smtp_password,
                    smtp_from=smtp_from,
                    to_email=to_email,
                    msg_raw=msg_raw,
                )
                return True, "ok"
            except Exception as exc:
                last_error = f"mode={mode} port={port} error={exc}"
        raise RuntimeError(last_error)
    except Exception as exc:
        err_text = str(exc).lower()
        print(f"[MAILER][ERROR] Failed to send email with attachments to {to_email}: {exc}")
        if "unreachable" in err_text or "network is unreachable" in err_text or "[errno 101]" in err_text:
            print(
                "[MAILER][HINT] منصات مثل Render غالبًا تحجب SMTP. عيّن MAIL_PROVIDER=resend وRESEND_API_KEY (HTTPS)."
            )
        return False, str(exc)

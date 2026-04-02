import os
import smtplib
from concurrent.futures import Future, ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import pywhatkit  # type: ignore
except Exception:
    pywhatkit = None

MAILER_ASYNC_WORKERS = int(os.getenv("MAILER_ASYNC_WORKERS", "2"))
_MAILER_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, MAILER_ASYNC_WORKERS))


def _smtp_transport_mode() -> str:
    mode = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
    if mode in {"ssl", "tls"}:
        return "ssl"
    if mode in {"none", "plain"}:
        return "none"
    return "starttls"


def _mailer_delivery_mode() -> str:
    mode = os.getenv("MAILER_DELIVERY_MODE", "async").strip().lower()
    if mode in {"sync", "synchronous"}:
        return "sync"
    return "async"


def _looks_like_placeholder(value: str) -> bool:
    stripped = value.strip()
    normalized = stripped.upper()
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return normalized in {
        "",
        "PUT_YOUR_GMAIL_APP_PASSWORD_HERE",
        "CHANGE_ME",
        "YOUR_APP_PASSWORD",
    }


def _parse_smtp_port(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        return 587


def _build_smtp_attempts(smtp_host: str, smtp_port: int, smtp_security: str) -> list[tuple[str, int]]:
    # Start with user-configured mode/port, then try pragmatic Gmail fallback.
    attempts: list[tuple[str, int]] = [(smtp_security, smtp_port)]
    host = smtp_host.strip().lower()
    if host in {"smtp.gmail.com", "smtp.googlemail.com"}:
        if (smtp_security, smtp_port) != ("starttls", 587):
            attempts.append(("starttls", 587))
        if (smtp_security, smtp_port) != ("ssl", 465):
            attempts.append(("ssl", 465))

    deduped: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for item in attempts:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _send_smtp_message(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_security: str,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    to_email: str,
    msg_raw: str,
) -> None:
    if smtp_security == "ssl":
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_email], msg_raw)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if smtp_security == "starttls":
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [to_email], msg_raw)


def _brand_email_html(
    *,
    app_name: str,
    title: str,
    recipient_name: str,
    intro: str,
    cta_label: str,
    cta_url: str,
) -> str:
    support_email = os.getenv("SMTP_FROM", "support@maestroyoga.local").strip()
    return f"""
<div dir="rtl" style="margin:0;background:#f8fafc;padding:24px 12px;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #d1fae5;border-radius:14px;overflow:hidden;">
    <div style="padding:18px 22px;background:linear-gradient(135deg,#0f766e,#10b981);color:#ffffff;">
      <div style="font-family:Arial,sans-serif;font-size:12px;opacity:.9;letter-spacing:.8px;text-transform:uppercase;">Maestro Yoga</div>
      <div style="font-family:Arial,sans-serif;font-size:21px;font-weight:700;line-height:1.3;margin-top:4px;">{title}</div>
    </div>
    <div style="padding:22px 22px 16px;font-family:Arial,sans-serif;color:#0f172a;line-height:1.7;">
      <p style="margin:0 0 10px;">مرحبًا {recipient_name}،</p>
      <p style="margin:0 0 16px;">{intro}</p>
      <p style="margin:0 0 18px;">
        <a href="{cta_url}" style="display:inline-block;background:#0f766e;color:#ffffff;text-decoration:none;padding:11px 18px;border-radius:8px;font-weight:700;">
          {cta_label}
        </a>
      </p>
      <p style="margin:0 0 6px;font-size:13px;color:#475569;">إذا لم يعمل الزر، استخدم هذا الرابط:</p>
      <p style="margin:0 0 14px;font-size:13px;word-break:break-all;"><a href="{cta_url}" style="color:#0f766e;">{cta_url}</a></p>
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;">
        <div>{app_name}</div>
        <div>الدعم: {support_email}</div>
      </div>
    </div>
  </div>
</div>
""".strip()


def _send_mail(to_email: str, subject: str, body: str, html_body: str | None = None) -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = _parse_smtp_port(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "no-reply@maestroyoga.local")
    mail_provider = os.getenv("MAIL_PROVIDER", "smtp").strip().lower()
    smtp_security = _smtp_transport_mode()

    if not smtp_host:
        return False, "missing_smtp_host"
    if _looks_like_placeholder(smtp_password):
        return False, "invalid_smtp_password_placeholder"
    if not smtp_user:
        return False, "missing_smtp_user"

    try:
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
        print(f"[MAILER][ERROR] Failed to send email to {to_email}: {exc}")
        return False, str(exc)


def _log_mail_future(prefix: str, fut: Future[tuple[bool, str]]) -> None:
    try:
        ok, info = fut.result()
        if not ok:
            print(f"[MAILER][ERROR] {prefix} failed asynchronously: {info}")
    except Exception as exc:
        print(f"[MAILER][ERROR] {prefix} crashed asynchronously: {exc}")


def validate_mailer_settings() -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    if not smtp_host:
        return False, "missing_smtp_host"
    if not smtp_user:
        return False, "missing_smtp_user"
    if _looks_like_placeholder(smtp_password):
        return False, "invalid_smtp_password_placeholder"
    return True, "ok"


def send_email_verification_email(to_email: str, verification_url: str, full_name: str = "") -> tuple[bool, str]:
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    recipient_name = full_name.strip() or "there"

    subject = f"{app_name} - تأكيد البريد الإلكتروني"
    body = (
        f"مرحبًا بك في {app_name}!\n\n"
        f"يرجى تأكيد بريدك الإلكتروني عبر الرابط التالي:\n{verification_url}\n\n"
        "إذا لم تطلب إنشاء هذا الحساب يمكنك تجاهل هذه الرسالة."
    )
    html_body = _brand_email_html(
        app_name=app_name,
        title="تأكيد البريد الإلكتروني",
        recipient_name=recipient_name,
        intro="يرجى تأكيد بريدك الإلكتروني لتفعيل الحساب ومتابعة الحجز والاشتراكات.",
        cta_label="تأكيد البريد",
        cta_url=verification_url,
    )
    return _send_mail(to_email, subject, body, html_body=html_body)


def send_password_reset_email(to_email: str, reset_url: str, full_name: str = "") -> tuple[bool, str]:
    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    recipient_name = full_name.strip() or "there"
    subject = f"{app_name} - إعادة تعيين كلمة المرور"
    body = (
        f"استلمنا طلبًا لإعادة تعيين كلمة المرور لحسابك في {app_name}.\n\n"
        f"افتح الرابط التالي للمتابعة:\n{reset_url}\n\n"
        "إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة."
    )
    html_body = _brand_email_html(
        app_name=app_name,
        title="إعادة تعيين كلمة المرور",
        recipient_name=recipient_name,
        intro="استلمنا طلبًا لإعادة تعيين كلمة المرور. استخدم الزر التالي للمتابعة بشكل آمن.",
        cta_label="إعادة تعيين كلمة المرور",
        cta_url=reset_url,
    )
    return _send_mail(to_email, subject, body, html_body=html_body)


def queue_email_verification_email(to_email: str, verification_url: str, full_name: str = "") -> tuple[bool, str]:
    ok, reason = validate_mailer_settings()
    if not ok:
        return False, reason
    if _mailer_delivery_mode() == "sync":
        return send_email_verification_email(to_email, verification_url, full_name)
    fut = _MAILER_EXECUTOR.submit(send_email_verification_email, to_email, verification_url, full_name)
    fut.add_done_callback(lambda done: _log_mail_future("email_verification", done))
    return True, "queued"


def queue_password_reset_email(to_email: str, reset_url: str, full_name: str = "") -> tuple[bool, str]:
    ok, reason = validate_mailer_settings()
    if not ok:
        return False, reason
    if _mailer_delivery_mode() == "sync":
        return send_password_reset_email(to_email, reset_url, full_name)
    fut = _MAILER_EXECUTOR.submit(send_password_reset_email, to_email, reset_url, full_name)
    fut.add_done_callback(lambda done: _log_mail_future("password_reset", done))
    return True, "queued"

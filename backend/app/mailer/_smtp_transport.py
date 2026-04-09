"""Low-level SMTP send and Gmail-friendly retry order."""

from __future__ import annotations

import smtplib


def _build_smtp_attempts(smtp_host: str, smtp_port: int, smtp_security: str) -> list[tuple[str, int]]:
    # لـ Gmail: جرّب 587 + STARTTLS أولًا (أكثر توافقًا؛ بعض الاستضافات تحجب 465 فقط).
    attempts: list[tuple[str, int]] = []
    host = smtp_host.strip().lower()
    if host in {"smtp.gmail.com", "smtp.googlemail.com"}:
        attempts.append(("starttls", 587))
        attempts.append((smtp_security, smtp_port))
        if (smtp_security, smtp_port) != ("ssl", 465):
            attempts.append(("ssl", 465))
    else:
        attempts.append((smtp_security, smtp_port))

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

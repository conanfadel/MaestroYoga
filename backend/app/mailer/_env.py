"""Environment-driven mailer configuration helpers."""

from __future__ import annotations

import os

MAILER_ASYNC_WORKERS = int(os.getenv("MAILER_ASYNC_WORKERS", "2"))


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


def _relay_endpoint() -> str:
    return os.getenv("MAIL_RELAY_URL", os.getenv("APPS_SCRIPT_WEBHOOK_URL", "")).strip()


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
        "RE_PLACEHOLDER",
    }


def _parse_smtp_port(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        return 587

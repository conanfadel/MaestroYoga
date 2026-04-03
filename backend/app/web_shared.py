import os
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from fastapi import Request


def _public_base(request: Request) -> str:
    """قاعدة الروابط العامة (روابط التحقق والدفع). يُفضّل PUBLIC_BASE_URL في الإنتاج خلف البروكسي."""
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url:
        return public_base_url
    return str(request.base_url).rstrip("/")


def _is_email_verification_required() -> bool:
    value = os.getenv("PUBLIC_REQUIRE_EMAIL_VERIFICATION", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _sanitize_next_url(next_url: str | None, fallback: str = "/index?center_id=1") -> str:
    candidate = (next_url or "").strip()
    if not candidate:
        return fallback
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return fallback
    if not parsed.path.startswith("/"):
        return fallback
    return candidate


def _normalize_phone_with_country(country_code: str, phone: str) -> str | None:
    cc = country_code.strip()
    if not cc.startswith("+") or not cc[1:].isdigit():
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return None

    if cc == "+966":
        if digits.startswith("0"):
            digits = digits[1:]
        if digits.startswith("966"):
            digits = digits[3:]
        if len(digits) != 9 or not digits.startswith("5"):
            return None
        return f"{cc}{digits}"

    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) < 7 or len(digits) > 12:
        return None
    return f"{cc}{digits}"


def _is_strong_public_password(password: str) -> bool:
    if len(password) < 8:
        return False
    if not any(c.isupper() for c in password):
        return False
    if not any(c.islower() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    if not any(not c.isalnum() and not c.isspace() for c in password):
        return False
    return True


def _plan_duration_days(plan_type: str) -> int:
    mapping = {
        "weekly": 7,
        "monthly": 30,
        "yearly": 365,
    }
    return mapping.get(plan_type, 30)


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


def _url_with_params(path: str, **params: str) -> str:
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    if not clean:
        return path
    return f"{path}?{urlencode(clean)}"


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cookie_secure_flag(request: Request) -> bool:
    cookie_secure = os.getenv("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}
    if cookie_secure:
        return True
    return request.url.scheme == "https"

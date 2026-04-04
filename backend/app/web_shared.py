import os
import re
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit

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


def _mail_fail_reason_query_token(raw: str | None) -> str:
    """يُمرَّر في query عند فشل الإرسال؛ فقط رموز داخلية آمنة (بدون مسافات أو حقن)."""
    s = (raw or "").strip().lower()
    if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", s):
        return s
    return ""


def public_mail_fail_why_token(raw: str | None) -> str:
    """يُشتقّ من رسالة فشل الإرسال الطويلة رمزًا آمناً لـ query (?why=) يُعرَض للمستخدم."""
    s = (raw or "").strip()
    low = s.lower()
    if "resend_http_403" in low and (
        "testing emails" in low or "verify a domain" in low or "validation_error" in low
    ):
        return "resend_sandbox_domain"
    return _mail_fail_reason_query_token(s)


def _url_with_params(path: str, **params: str) -> str:
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    if not clean:
        return path
    return f"{path}?{urlencode(clean)}"


def public_index_url_from_next(
    next_url: str | None,
    *,
    msg: str | None = None,
    fallback: str = "/index?center_id=1",
) -> str:
    """رابط الواجهة العامة /index مع center_id مأخوذ من next (بعد التحقق من البريد أو زيارة verify-pending وهو موثّق)."""
    safe = _sanitize_next_url(next_url, fallback=fallback)
    parsed = urlsplit(safe)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    cid = "1"
    if "center_id" in qs and qs["center_id"]:
        try:
            cid = str(int(qs["center_id"][0]))
        except (ValueError, IndexError):
            pass
    if msg:
        return _url_with_params("/index", center_id=cid, msg=msg)
    return _url_with_params("/index", center_id=cid)


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cookie_secure_flag(request: Request) -> bool:
    cookie_secure = os.getenv("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}
    if cookie_secure:
        return True
    return request.url.scheme == "https"

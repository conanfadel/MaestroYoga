"""Parse admin discount fields (percentage vs fixed reduction) and discount time windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .time_utils import utc_naive_to_ksa

DiscountMode = Literal["none", "percent", "fixed"]
ScheduleType = Literal["always", "date_range", "daily_hours"]


def normalize_discount_mode(raw: str | None) -> DiscountMode:
    v = (raw or "").strip().lower()
    if v in ("percent", "fixed"):
        return v  # type: ignore[return-value]
    return "none"


def normalize_schedule_type(raw: str | None) -> ScheduleType:
    v = (raw or "").strip().lower()
    if v in ("date_range", "daily_hours"):
        return v  # type: ignore[return-value]
    return "always"


@dataclass(frozen=True)
class ParsedDiscountPrice:
    list_price: float
    effective_price: float
    discount_mode: DiscountMode
    discount_percent: float | None


@dataclass(frozen=True)
class ParsedDiscountSchedule:
    schedule_type: ScheduleType
    valid_from: datetime | None
    valid_until: datetime | None
    hour_start: int | None
    hour_end: int | None


def _parse_float_loose(raw: str | None, *, field_label: str) -> tuple[float | None, str | None]:
    s = (raw or "").strip().replace(",", ".")
    if s == "":
        return None, None
    try:
        return float(s), None
    except ValueError:
        return None, f"{field_label} غير صالح"


def _parse_datetime_loose(raw: str | None) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            return None


def parse_admin_discount_pricing(
    *,
    list_price_raw: str,
    discount_mode_raw: str | None,
    discount_percent_raw: str | None,
    reduced_price_raw: str | None,
) -> tuple[ParsedDiscountPrice | None, str | None]:
    """Returns (parsed, error_message). error_message is user-facing Arabic for redirects."""
    lp, err = _parse_float_loose(list_price_raw, field_label="السعر الأساسي")
    if err:
        return None, err
    if lp is None or lp < 0:
        return None, "السعر الأساسي مطلوب ويجب أن يكون صفرًا أو أكبر"
    mode = normalize_discount_mode(discount_mode_raw)

    if mode == "none":
        return (
            ParsedDiscountPrice(
                list_price=float(lp),
                effective_price=float(lp),
                discount_mode="none",
                discount_percent=None,
            ),
            None,
        )

    if mode == "percent":
        pct, perr = _parse_float_loose(discount_percent_raw, field_label="نسبة الخصم")
        if perr:
            return None, perr
        if pct is None:
            return None, "أدخل نسبة الخصم"
        if pct < 0 or pct > 100:
            return None, "نسبة الخصم يجب أن تكون بين 0 و 100"
        effective = round(float(lp) * (1.0 - float(pct) / 100.0), 2)
        if effective < 0:
            effective = 0.0
        pct_val = float(pct)
        return (
            ParsedDiscountPrice(
                list_price=float(lp),
                effective_price=effective,
                discount_mode="percent",
                discount_percent=pct_val,
            ),
            None,
        )

    red, rerr = _parse_float_loose(reduced_price_raw, field_label="السعر المخفض")
    if rerr:
        return None, rerr
    if red is None:
        return None, "أدخل السعر المخفض"
    if red < 0:
        return None, "السعر المخفض لا يمكن أن يكون سالبًا"
    if red > float(lp) + 1e-9:
        return None, "السعر المخفض لا يجوز أن يتجاوز السعر الأساسي"
    return (
        ParsedDiscountPrice(
            list_price=float(lp),
            effective_price=float(red),
            discount_mode="fixed",
            discount_percent=None,
        ),
        None,
    )


def parse_admin_discount_schedule(
    *,
    discount_mode: str,
    schedule_type_raw: str | None,
    valid_from_raw: str | None,
    valid_until_raw: str | None,
    hour_start_raw: str | None,
    hour_end_raw: str | None,
) -> tuple[ParsedDiscountSchedule | None, str | None]:
    """Parse discount validity; when discount_mode is none, returns always with nulls."""
    if normalize_discount_mode(discount_mode) == "none":
        return ParsedDiscountSchedule("always", None, None, None, None), None

    st = normalize_schedule_type(schedule_type_raw)
    if st == "always":
        return ParsedDiscountSchedule("always", None, None, None, None), None

    if st == "date_range":
        vf = _parse_datetime_loose(valid_from_raw)
        vu = _parse_datetime_loose(valid_until_raw)
        if vf is None or vu is None:
            return None, "أدخل تاريخ ووقت البداية والنهاية للعرض"
        if vu < vf:
            return None, "تاريخ نهاية العرض يجب أن يكون بعد البداية"
        return ParsedDiscountSchedule("date_range", vf, vu, None, None), None

    # daily_hours — ساعات اليوم بتوقيت السعودية
    hs, herr = _parse_int_hour(hour_start_raw, "بداية النافذة")
    if herr:
        return None, herr
    he, herr2 = _parse_int_hour(hour_end_raw, "نهاية النافذة")
    if herr2:
        return None, herr2
    if hs is None or he is None:
        return None, "أدخل ساعة البداية والنهاية (0–23)"
    return ParsedDiscountSchedule("daily_hours", None, None, hs, he), None


def _parse_int_hour(raw: str | None, label: str) -> tuple[int | None, str | None]:
    s = (raw or "").strip()
    if s == "":
        return None, None
    try:
        n = int(s)
    except ValueError:
        return None, f"{label} غير صالحة"
    if n < 0 or n > 23:
        return None, f"{label} يجب أن تكون بين 0 و 23"
    return n, None


def _numeric_promo(list_price: float | None, effective: float) -> bool:
    lp = float(list_price) if list_price is not None else float(effective)
    return lp > float(effective) + 1e-6


def _schedule_fields(obj: Any) -> tuple[str, datetime | None, datetime | None, int | None, int | None]:
    st = getattr(obj, "discount_schedule_type", None) or "always"
    vf = getattr(obj, "discount_valid_from", None)
    vu = getattr(obj, "discount_valid_until", None)
    hs = getattr(obj, "discount_hour_start", None)
    he = getattr(obj, "discount_hour_end", None)
    return str(st), vf, vu, hs, he


def is_discount_schedule_active(
    now: datetime,
    *,
    schedule_type: str | None,
    valid_from: datetime | None,
    valid_until: datetime | None,
    hour_start: int | None,
    hour_end: int | None,
) -> bool:
    st = normalize_schedule_type(schedule_type)
    if st == "always":
        return True
    if st == "date_range":
        if valid_from is None or valid_until is None:
            return True
        return valid_from <= now <= valid_until
    if st == "daily_hours":
        if hour_start is None or hour_end is None:
            return True
        h = utc_naive_to_ksa(now).hour
        a, b = int(hour_start), int(hour_end)
        if a == b:
            return True
        if a < b:
            return a <= h <= b
        return h >= a or h <= b
    return True


def session_public_checkout_amount(session: Any, *, now: datetime | None = None) -> float:
    from .time_utils import utcnow_naive

    now = now or utcnow_naive()
    list_p = getattr(session, "list_price", None)
    eff = float(session.price_drop_in)
    if not _numeric_promo(list_p, eff):
        return eff
    st, vf, vu, hs, he = _schedule_fields(session)
    if is_discount_schedule_active(now, schedule_type=st, valid_from=vf, valid_until=vu, hour_start=hs, hour_end=he):
        return eff
    return float(list_p) if list_p is not None else eff


def plan_public_checkout_amount(plan: Any, *, now: datetime | None = None) -> float:
    from .time_utils import utcnow_naive

    now = now or utcnow_naive()
    list_p = getattr(plan, "list_price", None)
    eff = float(plan.price)
    if not _numeric_promo(list_p, eff):
        return eff
    st, vf, vu, hs, he = _schedule_fields(plan)
    if is_discount_schedule_active(now, schedule_type=st, valid_from=vf, valid_until=vu, hour_start=hs, hour_end=he):
        return eff
    return float(list_p) if list_p is not None else eff


def public_promo_label(*, discount_mode: str | None, discount_percent: float | None, list_price: float, effective: float) -> str:
    """Short Arabic label for index cards."""
    if list_price <= effective + 1e-6:
        return ""
    m = normalize_discount_mode(discount_mode)
    if m == "percent" and discount_percent is not None:
        n = discount_percent
        if n == int(n):
            pct_s = str(int(n))
        else:
            pct_s = f"{n:g}"
        return f"خصم بنسبة {pct_s}%"
    return "تخفيض"


def public_promo_schedule_caption(
    *,
    schedule_type: str | None,
    valid_from: datetime | None,
    valid_until: datetime | None,
    hour_start: int | None,
    hour_end: int | None,
) -> str:
    """Arabic line describing when the discount applies (for the public index)."""
    st = normalize_schedule_type(schedule_type)
    if st == "always":
        return "العرض ساري الآن"
    if st == "date_range" and valid_from and valid_until:
        a = utc_naive_to_ksa(valid_from).strftime("%Y-%m-%d %H:%M")
        b = utc_naive_to_ksa(valid_until).strftime("%Y-%m-%d %H:%M")
        return f"فترة العرض: من {a} إلى {b} (بتوقيت السعودية)"
    if st == "daily_hours" and hour_start is not None and hour_end is not None:
        return f"يوميًا من الساعة {hour_start}:00 إلى {hour_end}:00 (بتوقيت السعودية)"
    return ""


def public_show_promo_ui(
    obj: Any,
    *,
    list_price: float,
    checkout: float,
    discount_mode: str | None,
    now: datetime | None = None,
) -> bool:
    """Whether to show strikethrough + promo labels (schedule must be active)."""
    from .time_utils import utcnow_naive

    now = now or utcnow_naive()
    if normalize_discount_mode(discount_mode) == "none":
        return False
    if list_price <= checkout + 1e-6:
        return False
    st, vf, vu, hs, he = _schedule_fields(obj)
    return is_discount_schedule_active(now, schedule_type=st, valid_from=vf, valid_until=vu, hour_start=hs, hour_end=he)


def public_in_active_offer(obj: Any, *, list_price: float, checkout: float, discount_mode: str | None, now: datetime | None = None) -> bool:
    """Shown in «عروضنا»: numeric discount/reduction and schedule window active."""
    return public_show_promo_ui(obj, list_price=list_price, checkout=checkout, discount_mode=discount_mode, now=now)

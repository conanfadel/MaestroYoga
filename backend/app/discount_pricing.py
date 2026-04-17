"""Parse admin discount fields (percentage vs fixed reduction) and discount time windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from .time_utils import KSA_TZ, utc_naive_to_ksa

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
    duration_hours: int | None = None


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
        return None, f"السعر المخفض ({float(red):.2f} ر.س) لا يجوز أن يتجاوز السعر الأساسي ({float(lp):.2f} ر.س)."
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
    duration_hours_raw: str | None = None,
) -> tuple[ParsedDiscountSchedule | None, str | None]:
    """Parse discount validity; when discount_mode is none, returns always with nulls."""
    if normalize_discount_mode(discount_mode) == "none":
        return ParsedDiscountSchedule("always", None, None, None, None, None), None

    st = normalize_schedule_type(schedule_type_raw)
    if st == "always":
        return ParsedDiscountSchedule("always", None, None, None, None, None), None

    if st == "date_range":
        vf = _parse_datetime_loose(valid_from_raw)
        vu = _parse_datetime_loose(valid_until_raw)
        if vf is None or vu is None:
            return None, "أدخل تاريخ ووقت البداية والنهاية للعرض"
        if vu < vf:
            return None, "تاريخ نهاية العرض يجب أن يكون بعد البداية"
        return ParsedDiscountSchedule("date_range", vf, vu, None, None, None), None

    # daily_hours — أول N ساعة من منتصف ليل السعودية (أو نافذة 0–23 للبيانات القديمة)
    dur_s = (duration_hours_raw or "").strip()
    if dur_s:
        n, derr = _parse_duration_hours(dur_s)
        if derr:
            return None, derr
        if n is None:
            return None, "أدخل عدد الساعات للنافذة اليومية"
        return ParsedDiscountSchedule("daily_hours", None, None, None, None, duration_hours=int(n)), None
    hs, herr = _parse_int_hour(hour_start_raw, "بداية النافذة")
    if herr:
        return None, herr
    he, herr2 = _parse_int_hour(hour_end_raw, "نهاية النافذة")
    if herr2:
        return None, herr2
    if hs is None or he is None:
        return None, "أدخل عدد الساعات للنافذة اليومية (مثال: 2 أو 24)، أو ساعة البداية والنهاية (0–23) للبيانات القديمة"
    return ParsedDiscountSchedule("daily_hours", None, None, hs, he, None), None


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


def _parse_duration_hours(raw: str) -> tuple[int | None, str | None]:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return None, None
    try:
        n = int(float(s))
    except ValueError:
        return None, "عدد الساعات غير صالح"
    if n < 1 or n > 168:
        return None, "عدد الساعات يجب أن يكون بين 1 و 168"
    return n, None


def _ksa_hours_since_midnight(now_naive: datetime) -> float:
    k = utc_naive_to_ksa(now_naive)
    midnight = k.replace(hour=0, minute=0, second=0, microsecond=0)
    return (k - midnight).total_seconds() / 3600.0


def _stored_effective_price(obj: Any) -> float:
    if hasattr(obj, "price_drop_in"):
        return float(obj.price_drop_in)
    return float(getattr(obj, "price", 0.0))


def resolve_display_list_price(obj: Any) -> float:
    """السعر الأساسي للعرض (من العمود أو مُستنتج من نسبة الخصم)."""
    eff = _stored_effective_price(obj)
    lp_raw = getattr(obj, "list_price", None)
    if lp_raw is not None:
        return float(lp_raw)
    mode = normalize_discount_mode(getattr(obj, "discount_mode", None))
    if mode == "percent":
        pct = getattr(obj, "discount_percent", None)
        if pct is not None:
            p = float(pct)
            if 0 < p < 100:
                return round(eff / (1.0 - p / 100.0), 2)
    return eff


def is_discount_schedule_active(now: datetime, obj: Any) -> bool:
    st = normalize_schedule_type(getattr(obj, "discount_schedule_type", None))
    if st == "always":
        return True
    if st == "date_range":
        vf = getattr(obj, "discount_valid_from", None)
        vu = getattr(obj, "discount_valid_until", None)
        if vf is None or vu is None:
            return True
        return vf <= now <= vu
    if st == "daily_hours":
        dur = getattr(obj, "discount_duration_hours", None)
        if dur is not None and int(dur) > 0:
            h = _ksa_hours_since_midnight(now)
            return 0.0 <= h < float(int(dur))
        hour_start = getattr(obj, "discount_hour_start", None)
        hour_end = getattr(obj, "discount_hour_end", None)
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
    eff = float(session.price_drop_in)
    list_p = resolve_display_list_price(session)
    if not (list_p > eff + 1e-6):
        return eff
    if is_discount_schedule_active(now, session):
        return eff
    lp_stored = getattr(session, "list_price", None)
    return float(lp_stored) if lp_stored is not None else list_p


def plan_public_checkout_amount(plan: Any, *, now: datetime | None = None) -> float:
    from .time_utils import utcnow_naive

    now = now or utcnow_naive()
    eff = float(plan.price)
    list_p = resolve_display_list_price(plan)
    if not (list_p > eff + 1e-6):
        return eff
    if is_discount_schedule_active(now, plan):
        return eff
    lp_stored = getattr(plan, "list_price", None)
    return float(lp_stored) if lp_stored is not None else list_p


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
    duration_hours: int | None = None,
) -> str:
    """Arabic line describing when the discount applies (for the public index)."""
    st = normalize_schedule_type(schedule_type)
    if st == "always":
        return "العرض ساري الآن"
    if st == "date_range" and valid_from and valid_until:
        a = utc_naive_to_ksa(valid_from).strftime("%Y-%m-%d %H:%M")
        b = utc_naive_to_ksa(valid_until).strftime("%Y-%m-%d %H:%M")
        return f"فترة العرض: من {a} إلى {b} (بتوقيت السعودية)"
    if st == "daily_hours":
        if duration_hours is not None and int(duration_hours) > 0:
            return f"اليوم: أول {int(duration_hours)} ساعة من منتصف ليل السعودية (بتوقيت السعودية)"
        if hour_start is not None and hour_end is not None:
            return f"يوميًا من الساعة {hour_start}:00 إلى {hour_end}:00 (بتوقيت السعودية)"
    return ""


def public_show_promo_ui(obj: Any) -> bool:
    """عرض السعر المشطوب والوسوم: يوجد خصم مُعرَّف (قبل تطبيق نافذة الجدولة على السداد)."""
    if normalize_discount_mode(getattr(obj, "discount_mode", None)) == "none":
        return False
    eff = _stored_effective_price(obj)
    lp = resolve_display_list_price(obj)
    return lp > eff + 1e-6


def public_in_active_offer(obj: Any, *, now: datetime | None = None) -> bool:
    """ظهور في «عروضنا»: خصم مُعرَّف والنافذة الزمنية للعرض نشطة حاليًا."""
    from .time_utils import utcnow_naive

    now = now or utcnow_naive()
    if not public_show_promo_ui(obj):
        return False
    return is_discount_schedule_active(now, obj)


def promo_active_window_end_utc_naive(obj: Any, *, now: datetime | None = None) -> datetime | None:
    """نهاية النافذة الحالية للعرض بتوقيت UTC (بدون tz) — للعداد التنازلي على الفهرس."""
    from .time_utils import utcnow_naive

    now = now or utcnow_naive()
    if not public_show_promo_ui(obj):
        return None
    if not is_discount_schedule_active(now, obj):
        return None
    st = normalize_schedule_type(getattr(obj, "discount_schedule_type", None))
    if st == "always":
        return None
    if st == "date_range":
        return getattr(obj, "discount_valid_until", None)
    if st != "daily_hours":
        return None
    dur = getattr(obj, "discount_duration_hours", None)
    now_utc = now.replace(tzinfo=timezone.utc)
    ksa_now = now_utc.astimezone(KSA_TZ)
    mid = ksa_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if dur is not None and int(dur) > 0:
        end_ksa = mid + timedelta(hours=float(int(dur)))
    else:
        he = getattr(obj, "discount_hour_end", None)
        hs = getattr(obj, "discount_hour_start", None)
        if he is None or hs is None:
            return None
        a, b = int(hs), int(he)
        if a < b:
            end_ksa = mid + timedelta(hours=b + 1)
        else:
            return None
    return end_ksa.astimezone(timezone.utc).replace(tzinfo=None)

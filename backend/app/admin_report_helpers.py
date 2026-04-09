import os
from datetime import date, timedelta


def utf8_bom_csv_content(output) -> str:
    """BOM لعرض UTF-8 بشكل صحيح في Excel."""
    return "\ufeff" + output.getvalue()


def user_can_report_sessions(*, user, user_has_permission_fn) -> bool:
    return user_has_permission_fn(user, "sessions.manage") or user_has_permission_fn(
        user, "reports.financial"
    ) or user_has_permission_fn(user, "dashboard.view")


def user_can_report_revenue(*, user, user_has_permission_fn) -> bool:
    return user_has_permission_fn(user, "payments.records") or user_has_permission_fn(
        user, "reports.financial"
    ) or user_has_permission_fn(user, "dashboard.financial")


def report_period_to_range(
    *,
    period: str,
    date_from_s: str | None,
    date_to_s: str | None,
    parse_optional_date_fn,
    utcnow_fn,
) -> tuple[date, date, str, str | None]:
    """(start, end, label_ar, error_or_none)."""
    today = utcnow_fn().date()
    p = (period or "today").strip().lower()
    if p == "today":
        return today, today, "اليوم", None
    if p == "week":
        w0 = today - timedelta(days=today.weekday())
        w6 = w0 + timedelta(days=6)
        return w0, w6, "هذا الأسبوع (الإثنين–الأحد)", None
    if p == "month":
        first = today.replace(day=1)
        if first.month == 12:
            last = date(first.year, 12, 31)
        else:
            last = date(first.year, first.month + 1, 1) - timedelta(days=1)
        return first, last, "هذا الشهر", None
    if p == "year":
        y = today.year
        return date(y, 1, 1), date(y, 12, 31), f"السنة {y}", None
    if p == "custom":
        a = parse_optional_date_fn(date_from_s)
        b = parse_optional_date_fn(date_to_s)
        if not a or not b or a > b:
            return today, today, "", "أدخل تاريخ البداية والنهاية بصيغة YYYY-MM-DD ضمن فترة صحيحة."
        return a, b, f"من {a.isoformat()} إلى {b.isoformat()}", None
    return today, today, "اليوم", None


def report_previous_period_range(d0: date, d1: date) -> tuple[date, date, str]:
    span_days = (d1 - d0).days + 1
    if span_days < 1:
        span_days = 1
    prev_end = d0 - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span_days - 1)
    label = f"{prev_start.isoformat()} ← {prev_end.isoformat()}"
    return prev_start, prev_end, label


def vat_inclusive_breakdown(gross_total: float, vat_rate_percent: float) -> dict[str, float]:
    if gross_total <= 0 or vat_rate_percent <= 0:
        return {"gross": gross_total, "net": gross_total, "vat": 0.0}
    div = 1.0 + (vat_rate_percent / 100.0)
    net = gross_total / div
    vat_amt = gross_total - net
    return {"gross": gross_total, "net": net, "vat": vat_amt}


def effective_vat_percent_for_center(*, center) -> float:
    if center is not None and center.vat_rate_percent is not None:
        try:
            return float(center.vat_rate_percent)
        except (TypeError, ValueError):
            pass
    try:
        return float((os.getenv("VAT_RATE_PERCENT") or "15").strip() or "15")
    except ValueError:
        return 15.0


def payment_method_label_ar(method: str | None) -> str:
    m = (method or "").strip()
    return {
        "in_app_mock": "وهمي / تجريبي",
        "public_checkout": "دفع صفحة الحجز",
        "public_cart_checkout": "دفع السلة العامة",
    }.get(m, m or "—")


def parse_optional_non_negative_float(raw: str | None) -> float | None:
    s = (raw or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        v = float(s)
        return v if v >= 0 else None
    except ValueError:
        return None


def parse_optional_non_negative_int(raw: str | None) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        v = int(s)
        return v if v >= 0 else None
    except ValueError:
        return None

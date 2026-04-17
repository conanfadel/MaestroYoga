from .discount_pricing import (
    plan_public_checkout_amount,
    promo_active_window_end_utc_naive,
    public_in_active_offer,
    public_promo_label,
    public_promo_schedule_caption,
    public_show_promo_ui,
    resolve_display_list_price,
)
from .web_shared import _plan_duration_days


def default_plan_labels() -> dict[str, str]:
    return {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }


def build_public_plan_rows(plans: list, *, plan_labels: dict[str, str]) -> list[dict]:
    from .time_utils import utcnow_naive

    now = utcnow_naive()
    rows: list[dict] = []
    for p in plans:
        list_p = resolve_display_list_price(p)
        db_sale = float(p.price)
        checkout = plan_public_checkout_amount(p, now=now)
        mode = getattr(p, "discount_mode", None) or "none"
        pct = getattr(p, "discount_percent", None)
        if pct is not None:
            pct = float(pct)
        has_promo = public_show_promo_ui(p)
        promo_label = (
            public_promo_label(discount_mode=mode, discount_percent=pct, list_price=list_p, effective=db_sale)
            if has_promo
            else ""
        )
        st = getattr(p, "discount_schedule_type", None) or "always"
        vf = getattr(p, "discount_valid_from", None)
        vu = getattr(p, "discount_valid_until", None)
        hs = getattr(p, "discount_hour_start", None)
        he = getattr(p, "discount_hour_end", None)
        dh = getattr(p, "discount_duration_hours", None)
        promo_schedule = public_promo_schedule_caption(
            schedule_type=st,
            valid_from=vf,
            valid_until=vu,
            hour_start=hs,
            hour_end=he,
            duration_hours=int(dh) if dh is not None else None,
        )
        in_active_offer = public_in_active_offer(p, now=now)
        end_at = promo_active_window_end_utc_naive(p, now=now)
        rows.append(
            {
                "id": p.id,
                "name": p.name,
                "plan_type": p.plan_type,
                "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
                "duration_days": _plan_duration_days(p.plan_type),
                "price": checkout,
                "display_sale_price": db_sale,
                "list_price": list_p,
                "has_promo": has_promo,
                "promo_label": promo_label,
                "promo_schedule": promo_schedule,
                "in_active_offer": in_active_offer,
                "promo_countdown_end_iso": (end_at.isoformat() + "Z") if end_at else None,
                "session_limit": p.session_limit,
            }
        )
    return rows


def recommended_plan_id_by_daily_price(plan_rows: list[dict]) -> int | None:
    """Pick the plan with the lowest price per day (price / duration_days).

    When two plans tie on daily rate, the longer duration wins (e.g. yearly over monthly).
    With fewer than two plans, returns None so the UI does not show a comparative badge.
    """
    if len(plan_rows) < 2:
        return None
    best: tuple[float, float, int] | None = None
    for p in plan_rows:
        raw_id = p.get("id")
        if raw_id is None:
            continue
        d = int(p.get("duration_days") or 0)
        if d <= 0:
            d = 1
        price = float(p.get("price") or 0.0)
        score = price / float(d)
        pid = int(raw_id)
        cand = (score, -float(d), pid)
        if best is None or cand < best:
            best = cand
    return best[2] if best else None

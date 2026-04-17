from datetime import timedelta

from . import models
from .discount_pricing import (
    public_in_active_offer,
    public_promo_label,
    public_promo_schedule_caption,
    public_show_promo_ui,
    resolve_display_list_price,
    session_public_checkout_amount,
)
from .public_session_visibility import yoga_session_accepts_new_public_booking
from .time_utils import utcnow_naive
from .web_shared import _fmt_dt_weekday_ar


def build_public_session_rows(
    sessions: list[models.YogaSession],
    rooms_by_id: dict[int, models.Room],
    spots_by_session: dict[int, int],
    *,
    plan_session_booking_enabled: bool = False,
    plan_booked_session_ids: set[int] | None = None,
) -> list[dict]:
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    now = utcnow_naive()
    booked_ids = plan_booked_session_ids or set()
    rows: list[dict] = []
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        starts = s.starts_at
        dur = int(s.duration_minutes or 0)
        ends = (starts + timedelta(minutes=dur)) if starts else None
        list_p = resolve_display_list_price(s)
        db_sale = float(s.price_drop_in)
        checkout = session_public_checkout_amount(s, now=now)
        mode = getattr(s, "discount_mode", None) or "none"
        pct = getattr(s, "discount_percent", None)
        if pct is not None:
            pct = float(pct)
        has_promo = public_show_promo_ui(s)
        promo_label = (
            public_promo_label(discount_mode=mode, discount_percent=pct, list_price=list_p, effective=db_sale)
            if has_promo
            else ""
        )
        st = getattr(s, "discount_schedule_type", None) or "always"
        vf = getattr(s, "discount_valid_from", None)
        vu = getattr(s, "discount_valid_until", None)
        hs = getattr(s, "discount_hour_start", None)
        he = getattr(s, "discount_hour_end", None)
        dh = getattr(s, "discount_duration_hours", None)
        promo_schedule = public_promo_schedule_caption(
            schedule_type=st,
            valid_from=vf,
            valid_until=vu,
            hour_start=hs,
            hour_end=he,
            duration_hours=int(dh) if dh is not None else None,
        )
        in_active_offer = public_in_active_offer(s, now=now)
        rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt_weekday_ar(s.starts_at),
                "starts_at_iso": starts.isoformat() if starts else "",
                "ends_at_iso": ends.isoformat() if ends else "",
                "duration_minutes": s.duration_minutes,
                "price_drop_in": checkout,
                "display_sale_price": db_sale,
                "list_price": list_p,
                "has_promo": has_promo,
                "promo_label": promo_label,
                "promo_schedule": promo_schedule,
                "in_active_offer": in_active_offer,
                "room_name": room.name if room else "-",
                "spots_available": spots_by_session.get(int(s.id), 0),
                "allows_public_booking": yoga_session_accepts_new_public_booking(s, now=now),
                "use_plan_slot_cta": bool(plan_session_booking_enabled),
                "booked_via_plan": int(s.id) in booked_ids,
                "can_cancel_plan_slot": (int(s.id) in booked_ids)
                and yoga_session_accepts_new_public_booking(s, now=now),
            }
        )
    return rows

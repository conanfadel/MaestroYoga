"""برنامج ولاء حسب عدد الحجوزات بحالة confirmed لهذا المركز."""

import os
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models

LOYALTY_TIER_NONE = "none"
LOYALTY_TIER_BRONZE = "bronze"
LOYALTY_TIER_SILVER = "silver"
LOYALTY_TIER_GOLD = "gold"


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default)).strip()))
    except ValueError:
        return default


def loyalty_thresholds() -> tuple[int, int, int]:
    """(bronze_min, silver_min, gold_min) — كل مستوى يتطلب على الأقل هذا العدد من الجلسات المؤكدة."""
    silver = max(2, _int_env("LOYALTY_SILVER_MIN_CONFIRMED", 6))
    gold = max(silver + 1, _int_env("LOYALTY_GOLD_MIN_CONFIRMED", 20))
    bronze = max(1, min(_int_env("LOYALTY_BRONZE_MIN_CONFIRMED", 1), silver - 1))
    return bronze, silver, gold


def loyalty_tier_for_confirmed_count(count: int) -> str:
    bronze_min, silver_min, gold_min = loyalty_thresholds()
    if count >= gold_min:
        return LOYALTY_TIER_GOLD
    if count >= silver_min:
        return LOYALTY_TIER_SILVER
    if count >= bronze_min:
        return LOYALTY_TIER_BRONZE
    return LOYALTY_TIER_NONE


def loyalty_tier_label_ar(tier: str) -> str:
    return {
        LOYALTY_TIER_NONE: "بدون وسام",
        LOYALTY_TIER_BRONZE: "برونزي",
        LOYALTY_TIER_SILVER: "فضي",
        LOYALTY_TIER_GOLD: "ذهبي",
    }.get(tier, tier)


def loyalty_context_for_count(count: int) -> dict[str, Any]:
    bronze_min, silver_min, gold_min = loyalty_thresholds()
    tier = loyalty_tier_for_confirmed_count(count)
    next_need: int | None = None
    next_label = ""
    if tier == LOYALTY_TIER_NONE:
        next_need = bronze_min
        next_label = loyalty_tier_label_ar(LOYALTY_TIER_BRONZE)
    elif tier == LOYALTY_TIER_BRONZE:
        next_need = silver_min
        next_label = loyalty_tier_label_ar(LOYALTY_TIER_SILVER)
    elif tier == LOYALTY_TIER_SILVER:
        next_need = gold_min
        next_label = loyalty_tier_label_ar(LOYALTY_TIER_GOLD)
    sessions_to_next: int | None = None
    if next_need is not None:
        sessions_to_next = max(0, next_need - count)
    return {
        "loyalty_confirmed_count": count,
        "loyalty_tier": tier,
        "loyalty_tier_label": loyalty_tier_label_ar(tier),
        "loyalty_next_tier_label": next_label,
        "loyalty_sessions_to_next": sessions_to_next,
        "loyalty_thresholds": {"bronze": bronze_min, "silver": silver_min, "gold": gold_min},
    }


def count_confirmed_sessions_for_public_user(db: Session, center_id: int, public_user: models.PublicUser) -> int:
    email = (public_user.email or "").lower().strip()
    if not email:
        return 0
    return (
        db.query(models.Booking)
        .join(models.Client, models.Booking.client_id == models.Client.id)
        .filter(
            models.Client.center_id == center_id,
            func.lower(models.Client.email) == email,
            models.Booking.status == "confirmed",
        )
        .count()
    )


def loyalty_confirmed_counts_by_email_lower(db: Session, center_id: int) -> dict[str, int]:
    """كل البريد (lower) → عدد حجوزات confirmed في المركز."""
    rows = (
        db.query(func.lower(models.Client.email).label("em"), func.count(models.Booking.id))
        .select_from(models.Booking)
        .join(models.Client, models.Client.id == models.Booking.client_id)
        .filter(
            models.Client.center_id == center_id,
            models.Booking.status == "confirmed",
        )
        .group_by(func.lower(models.Client.email))
        .all()
    )
    out: dict[str, int] = {}
    for em, c in rows:
        if em:
            out[str(em).lower()] = int(c)
    return out

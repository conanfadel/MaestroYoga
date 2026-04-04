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

LOYALTY_REWARD_MAX_LEN = 800

# اقتراحات افتراضية تظهر للزائر حتى يخصّص المسؤول النصوص من لوحة الإدارة
DEFAULT_LOYALTY_REWARD_BRONZE = (
    "وسام «بداية المسيرة» — شارة ولاء في حسابك، وإشعارات بالعروض والفعاليات المناسبة للأعضاء النشطين."
)
DEFAULT_LOYALTY_REWARD_SILVER = (
    "وسام «التزام ملحوظ» — أولوية في فترات الحجز المبكرة عند إعلانها، ومزايا خصم أو هدايا عند حملات المركز الخاصة."
)
DEFAULT_LOYALTY_REWARD_GOLD = (
    "وسام «نجم المركز» — أعلى مستوى: جلسات أو خصومات استثنائية وفق سياسة المركز، ودعوات للفعاليات الحصرية."
)


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default)).strip()))
    except ValueError:
        return default


def loyalty_thresholds() -> tuple[int, int, int]:
    """عتبات افتراضية من متغيرات البيئة فقط (بدون إعدادات المركز)."""
    b = max(1, _int_env("LOYALTY_BRONZE_MIN_CONFIRMED", 1))
    s = max(2, _int_env("LOYALTY_SILVER_MIN_CONFIRMED", 6))
    g = max(_int_env("LOYALTY_GOLD_MIN_CONFIRMED", 20), s + 1)
    return apply_loyalty_cascade(b, s, g)


def apply_loyalty_cascade(bronze: int, silver: int, gold: int) -> tuple[int, int, int]:
    """يضمن: فضي ≥ برونزي + 1، ذهبي ≥ فضي + 1 (متسلسل دون تداخل)."""
    b = max(1, int(bronze))
    s = max(int(silver), b + 1)
    g = max(int(gold), s + 1)
    return b, s, g


def effective_loyalty_thresholds(center: models.Center | None) -> tuple[int, int, int]:
    """العتبات الفعلية: تخصيص المركز إن وُجد، ثم تطبيق التسلسل برونزي → فضي → ذهبي."""
    b, s, g = loyalty_thresholds()
    if not center:
        return b, s, g
    if center.loyalty_bronze_min is not None:
        b = max(1, int(center.loyalty_bronze_min))
    if center.loyalty_silver_min is not None:
        s = max(2, int(center.loyalty_silver_min))
    if center.loyalty_gold_min is not None:
        g = int(center.loyalty_gold_min)
    return apply_loyalty_cascade(b, s, g)


def loyalty_tier_for_confirmed_count(count: int, center: models.Center | None = None) -> str:
    bronze_min, silver_min, gold_min = effective_loyalty_thresholds(center)
    if count >= gold_min:
        return LOYALTY_TIER_GOLD
    if count >= silver_min:
        return LOYALTY_TIER_SILVER
    if count >= bronze_min:
        return LOYALTY_TIER_BRONZE
    return LOYALTY_TIER_NONE


def loyalty_tier_label_ar(tier: str, center: models.Center | None = None) -> str:
    defaults = {
        LOYALTY_TIER_NONE: "بدون وسام",
        LOYALTY_TIER_BRONZE: "برونزي",
        LOYALTY_TIER_SILVER: "فضي",
        LOYALTY_TIER_GOLD: "ذهبي",
    }
    if center:
        if tier == LOYALTY_TIER_BRONZE and (center.loyalty_label_bronze or "").strip():
            return (center.loyalty_label_bronze or "").strip()[:64]
        if tier == LOYALTY_TIER_SILVER and (center.loyalty_label_silver or "").strip():
            return (center.loyalty_label_silver or "").strip()[:64]
        if tier == LOYALTY_TIER_GOLD and (center.loyalty_label_gold or "").strip():
            return (center.loyalty_label_gold or "").strip()[:64]
    return defaults.get(tier, tier)


def loyalty_context_for_count(count: int, center: models.Center | None = None) -> dict[str, Any]:
    bronze_min, silver_min, gold_min = effective_loyalty_thresholds(center)
    tier = loyalty_tier_for_confirmed_count(count, center)
    next_need: int | None = None
    next_label = ""
    if tier == LOYALTY_TIER_NONE:
        next_need = bronze_min
        next_label = loyalty_tier_label_ar(LOYALTY_TIER_BRONZE, center)
    elif tier == LOYALTY_TIER_BRONZE:
        next_need = silver_min
        next_label = loyalty_tier_label_ar(LOYALTY_TIER_SILVER, center)
    elif tier == LOYALTY_TIER_SILVER:
        next_need = gold_min
        next_label = loyalty_tier_label_ar(LOYALTY_TIER_GOLD, center)
    sessions_to_next: int | None = None
    if next_need is not None:
        sessions_to_next = max(0, next_need - count)
    return {
        "loyalty_confirmed_count": count,
        "loyalty_tier": tier,
        "loyalty_tier_label": loyalty_tier_label_ar(tier, center),
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


def loyalty_reward_text(center: models.Center | None, tier_key: str) -> str:
    """tier_key: bronze | silver | gold"""
    defaults = {
        "bronze": DEFAULT_LOYALTY_REWARD_BRONZE,
        "silver": DEFAULT_LOYALTY_REWARD_SILVER,
        "gold": DEFAULT_LOYALTY_REWARD_GOLD,
    }
    base = defaults.get(tier_key, "")
    if not center:
        return base
    raw = {
        "bronze": center.loyalty_reward_bronze,
        "silver": center.loyalty_reward_silver,
        "gold": center.loyalty_reward_gold,
    }.get(tier_key)
    if raw and str(raw).strip():
        return str(raw).strip()[:LOYALTY_REWARD_MAX_LEN]
    return base


def loyalty_program_table_rows(center: models.Center | None) -> list[dict[str, Any]]:
    """صفوف جدول برنامج المكافآت للواجهة العامة."""
    b, s, g = effective_loyalty_thresholds(center)
    bronze_hi = s - 1
    silver_hi = g - 1
    rows: list[dict[str, Any]] = [
        {
            "tier_key": "bronze",
            "medal": "🥉",
            "label": loyalty_tier_label_ar(LOYALTY_TIER_BRONZE, center),
            "range_label": f"من {b} إلى {bronze_hi} جلسة مؤكدة" if bronze_hi >= b else f"من {b} جلسة",
            "reward": loyalty_reward_text(center, "bronze"),
            "row_class": "loyalty-program__row--bronze",
        },
        {
            "tier_key": "silver",
            "medal": "🥈",
            "label": loyalty_tier_label_ar(LOYALTY_TIER_SILVER, center),
            "range_label": f"من {s} إلى {silver_hi} جلسة مؤكدة" if silver_hi >= s else f"من {s} جلسة",
            "reward": loyalty_reward_text(center, "silver"),
            "row_class": "loyalty-program__row--silver",
        },
        {
            "tier_key": "gold",
            "medal": "🥇",
            "label": loyalty_tier_label_ar(LOYALTY_TIER_GOLD, center),
            "range_label": f"{g} جلسة مؤكدة فأكثر",
            "reward": loyalty_reward_text(center, "gold"),
            "row_class": "loyalty-program__row--gold",
        },
    ]
    return rows


def validate_loyalty_threshold_triple(bronze: int, silver: int, gold: int) -> str | None:
    """يُستدعى بعد apply_loyalty_cascade — حدود عليا فقط."""
    if bronze < 1:
        return "البرونزي يجب أن يبدأ من جلسة واحدة على الأقل."
    if gold > 5000 or silver > 5000 or bronze > 5000:
        return "القيم كبيرة جداً."
    return None

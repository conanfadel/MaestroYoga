"""عرض اشتراك العميل النشط في الواجهة العامة (الصفحة الرئيسية وحساب المستخدم)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .time_utils import utcnow_naive
from .web_shared import _fmt_dt


def empty_public_subscription_context(center_id: int) -> dict[str, object]:
    """قيم افتراضية حتى لا تفشل قوالب Jinja عند غياب اشتراك."""
    return {
        "public_sub_active": False,
        "public_sub_plan_name": "",
        "public_sub_plan_type_label": "",
        "public_sub_ends_at_display": "",
        "public_sub_starts_at_display": "",
        "public_sub_session_cap": False,
        "public_sub_sessions_used": 0,
        "public_sub_sessions_limit": None,
        "public_sub_sessions_remaining": None,
        "public_sub_at_cap": False,
        "public_sub_plan_slot_booking": False,
        "public_sub_book_url": f"/index?center_id={int(center_id)}#sessions-section",
    }


def count_confirmed_plan_sessions_in_period(
    db: Session,
    *,
    client_id: int,
    center_id: int,
    subscription: models.ClientSubscription,
) -> int:
    """جلسات مؤكدة ضمن [start_date, end_date] للاشتراك (نفس منطق العداد في الواجهة)."""
    raw = (
        db.query(func.count(models.Booking.id))
        .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
        .filter(
            models.Booking.client_id == client_id,
            models.Booking.center_id == center_id,
            models.Booking.status == "confirmed",
            models.YogaSession.starts_at >= subscription.start_date,
            models.YogaSession.starts_at <= subscription.end_date,
        )
        .scalar()
    )
    return int(raw or 0)


def get_active_subscription_bundle(
    db: Session,
    *,
    center_id: int,
    client_id: int,
    now: object | None = None,
) -> tuple[models.ClientSubscription, models.SubscriptionPlan] | None:
    """اشتراك نشط للعميل في المركز مع الخطة، أو None."""
    now = now or utcnow_naive()
    row = (
        db.query(models.ClientSubscription, models.SubscriptionPlan)
        .join(models.SubscriptionPlan, models.SubscriptionPlan.id == models.ClientSubscription.plan_id)
        .filter(
            models.ClientSubscription.client_id == client_id,
            models.ClientSubscription.status == "active",
            models.SubscriptionPlan.center_id == center_id,
            models.ClientSubscription.end_date >= now,
        )
        .order_by(models.ClientSubscription.end_date.desc())
        .first()
    )
    if not row:
        return None
    return row[0], row[1]


def build_public_active_subscription_context(
    db: Session,
    center_id: int,
    public_user: models.PublicUser | None,
    plan_labels: dict[str, str],
) -> dict[str, object]:
    """اشتراك نشط في المركز + عدّ جلسات مؤكدة ضمن فترة الاشتراك عند وجود حد للخطة."""
    base = empty_public_subscription_context(center_id)
    if not public_user:
        return base
    email = (public_user.email or "").strip().lower()
    if not email:
        return base
    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == email)
        .first()
    )
    if not client:
        return base
    bundle = get_active_subscription_bundle(db, center_id=center_id, client_id=client.id)
    if not bundle:
        return base
    sub, plan = bundle
    used_n = count_confirmed_plan_sessions_in_period(db, client_id=client.id, center_id=center_id, subscription=sub)
    limit_v = plan.session_limit
    cap = limit_v is not None and int(limit_v) > 0
    remaining: int | None = None
    at_cap = False
    if cap:
        lim = int(limit_v or 0)
        remaining = max(0, lim - used_n)
        at_cap = remaining <= 0
    plan_type_label = plan_labels.get(plan.plan_type, plan.plan_type)
    plan_slot_booking = bool(cap and not at_cap)
    return {
        **base,
        "public_sub_active": True,
        "public_sub_plan_name": plan.name,
        "public_sub_plan_type_label": plan_type_label,
        "public_sub_ends_at_display": _fmt_dt(sub.end_date),
        "public_sub_starts_at_display": _fmt_dt(sub.start_date),
        "public_sub_session_cap": cap,
        "public_sub_sessions_used": used_n,
        "public_sub_sessions_limit": int(limit_v) if cap else None,
        "public_sub_sessions_remaining": remaining,
        "public_sub_at_cap": at_cap,
        "public_sub_plan_slot_booking": plan_slot_booking,
    }

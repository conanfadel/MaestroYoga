import hashlib

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def compute_public_center_content_version(db: Session, center_id: int) -> str:
    center = db.get(models.Center, center_id)
    if not center:
        return "missing-center"
    sessions_count = (
        db.query(func.count(models.YogaSession.id)).filter(models.YogaSession.center_id == center_id).scalar() or 0
    )
    sessions_max_id = (
        db.query(func.max(models.YogaSession.id)).filter(models.YogaSession.center_id == center_id).scalar() or 0
    )
    rooms_count = db.query(func.count(models.Room.id)).filter(models.Room.center_id == center_id).scalar() or 0
    rooms_max_id = db.query(func.max(models.Room.id)).filter(models.Room.center_id == center_id).scalar() or 0
    plans_count = (
        db.query(func.count(models.SubscriptionPlan.id)).filter(models.SubscriptionPlan.center_id == center_id).scalar() or 0
    )
    plans_max_id = (
        db.query(func.max(models.SubscriptionPlan.id)).filter(models.SubscriptionPlan.center_id == center_id).scalar() or 0
    )
    plans_active_count = (
        db.query(func.count(models.SubscriptionPlan.id))
        .filter(models.SubscriptionPlan.center_id == center_id, models.SubscriptionPlan.is_active.is_(True))
        .scalar()
        or 0
    )
    faq_count = db.query(func.count(models.FAQItem.id)).filter(models.FAQItem.center_id == center_id).scalar() or 0
    faq_latest_upd = (
        db.query(func.max(models.FAQItem.updated_at)).filter(models.FAQItem.center_id == center_id).scalar() or ""
    )
    post_count = db.query(func.count(models.CenterPost.id)).filter(models.CenterPost.center_id == center_id).scalar() or 0
    post_latest_upd = (
        db.query(func.max(models.CenterPost.updated_at)).filter(models.CenterPost.center_id == center_id).scalar() or ""
    )
    payload = "|".join(
        [
            str(center.id),
            center.name or "",
            center.city or "",
            center.logo_url or "",
            center.brand_tagline or "",
            center.index_hero_heading_override or "",
            center.hero_image_url or "",
            "1" if center.hero_show_stock_photo else "0",
            center.index_config_json or "",
            str(sessions_count),
            str(sessions_max_id),
            str(rooms_count),
            str(rooms_max_id),
            str(plans_count),
            str(plans_max_id),
            str(plans_active_count),
            str(faq_count),
            str(faq_latest_upd),
            str(post_count),
            str(post_latest_upd),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

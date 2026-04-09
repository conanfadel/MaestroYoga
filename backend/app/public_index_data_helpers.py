from sqlalchemy import func, nullslast
from sqlalchemy.orm import Session

from . import models


def load_public_index_data(db: Session, center_id: int) -> dict:
    plans = (
        db.query(models.SubscriptionPlan)
        .filter(
            models.SubscriptionPlan.center_id == center_id,
            models.SubscriptionPlan.is_active.is_(True),
        )
        .order_by(models.SubscriptionPlan.price.asc())
        .all()
    )
    faq_items = (
        db.query(models.FAQItem)
        .filter(models.FAQItem.center_id == center_id, models.FAQItem.is_active.is_(True))
        .order_by(models.FAQItem.sort_order.asc(), models.FAQItem.created_at.asc())
        .all()
    )
    pinned_post = (
        db.query(models.CenterPost)
        .filter(
            models.CenterPost.center_id == center_id,
            models.CenterPost.is_published.is_(True),
            models.CenterPost.is_pinned.is_(True),
        )
        .order_by(nullslast(models.CenterPost.published_at.desc()), models.CenterPost.id.desc())
        .first()
    )
    total_published_posts = (
        db.query(func.count(models.CenterPost.id))
        .filter(
            models.CenterPost.center_id == center_id,
            models.CenterPost.is_published.is_(True),
        )
        .scalar()
        or 0
    )
    recent_posts = (
        db.query(models.CenterPost)
        .filter(models.CenterPost.center_id == center_id, models.CenterPost.is_published.is_(True))
        .order_by(nullslast(models.CenterPost.published_at.desc()), models.CenterPost.id.desc())
        .limit(24)
        .all()
    )
    return {
        "plans": plans,
        "faq_items": faq_items,
        "pinned_post": pinned_post,
        "total_published_posts": int(total_published_posts),
        "recent_posts": recent_posts,
    }

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


def build_public_index_template_context(
    *,
    request,
    center,
    rows: list,
    plans: list,
    payment,
    msg,
    public_user,
    faq_items: list,
    pinned_public_post,
    public_posts_teasers: list,
    news_ticker_items: list,
    public_news_meta: dict,
    plan_rows: list,
    index_page: dict,
    index_refund_p1_html: str,
    index_seo_title: str,
    index_meta_description: str,
    index_preconnect_origins_fn,
    loyalty_program_rows_fn,
    feedback_enabled: bool,
    public_content_version: str,
    loyalty_ctx: dict,
    analytics_ctx: dict,
    index_hero_app_name: str,
) -> dict:
    return {
        "center": center,
        "center_id": center.id,
        "index_page": index_page,
        "index_refund_p1_html": index_refund_p1_html,
        "sessions": rows,
        "plans": plan_rows,
        "payment": payment,
        "msg": msg,
        "public_user": public_user,
        "faq_items": faq_items,
        "pinned_public_post": pinned_public_post,
        "public_posts_teasers": public_posts_teasers,
        "news_ticker_items": news_ticker_items,
        "public_news_has_more": public_news_meta["public_news_has_more"],
        "public_news_list_url": public_news_meta["public_news_list_url"],
        "index_seo_title": index_seo_title,
        "index_meta_description": index_meta_description,
        "index_preconnect_origins": index_preconnect_origins_fn(
            request, center, pinned_public_post, public_posts_teasers
        ),
        "loyalty_program_rows": loyalty_program_rows_fn(center),
        "feedback_enabled": feedback_enabled,
        "public_content_version": public_content_version,
        **loyalty_ctx,
        **analytics_ctx,
        "index_hero_app_name": index_hero_app_name,
    }

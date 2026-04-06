"""Public-facing HTML routes."""
import csv
import io
import json
from html import escape as html_escape
from collections import defaultdict
from datetime import date, datetime, timedelta
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import and_, case, func, nullslast, or_
from sqlalchemy.orm import Session

from .. import models
from ..booking_utils import ACTIVE_BOOKING_STATUSES, spots_available
from ..bootstrap import DEMO_CENTER_NAME, ensure_demo_data, ensure_demo_news_posts
from ..database import get_db
from ..loyalty import (
    LOYALTY_REWARD_MAX_LEN,
    count_confirmed_sessions_for_public_user,
    effective_loyalty_thresholds,
    loyalty_confirmed_counts_by_email_lower,
    loyalty_context_for_count,
    loyalty_program_table_rows,
    loyalty_thresholds,
    validate_loyalty_threshold_triple,
)
from ..mailer import (
    feedback_destination_email,
    queue_email_verification_email,
    queue_password_reset_email,
    send_mail_with_attachments,
    validate_mailer_settings,
)
from ..payments import get_payment_provider, payment_provider_supports_hosted_checkout
from ..rate_limiter import rate_limiter
from ..request_ip import get_client_ip
from ..security_audit import log_security_event
from ..security import (
    create_access_token,
    create_public_access_token,
    create_public_email_verification_token,
    create_public_email_verify_flash_token,
    create_public_password_reset_token,
    decode_public_email_verification_token,
    decode_public_email_verify_flash_token,
    decode_public_password_reset_token,
    get_public_user_from_token_string,
    get_user_from_token_string,
    hash_password,
    require_roles_cookie_or_bearer,
    verify_password,
)
from ..tenant_utils import require_user_center_id
from ..time_utils import utcnow_naive
from ..web_shared import (
    _cookie_secure_flag,
    _fmt_dt,
    _fmt_dt_weekday_ar,
    _is_email_verification_required,
    _is_strong_public_password,
    _is_truthy_env,
    _normalize_phone_with_country,
    _plan_duration_days,
    _public_base,
    _sanitize_next_url,
    PUBLIC_INDEX_DEFAULT_PATH,
    public_center_id_str_from_next,
    public_index_url_from_next,
    public_mail_fail_why_token,
    _url_with_params,
)
from .constants import *
from .helpers import *
from .router import router
from .templates_env import templates

@router.get("/index", response_class=HTMLResponse)
def public_index(
    request: Request,
    center_id: int = 1,
    payment: str | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
):
    public_user = _current_public_user(request, db)
    center = db.get(models.Center, center_id)
    if not center:
        # Keep web pages usable even on a fresh DB.
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
        if not center:
            center = db.query(models.Center).order_by(models.Center.id.asc()).first()
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    if center.name == DEMO_CENTER_NAME:
        ensure_demo_news_posts(db, center.id)

    _clear_center_branding_urls_if_files_missing(db, center)

    sessions = (
        db.query(models.YogaSession)
        .filter(models.YogaSession.center_id == center_id)
        .order_by(models.YogaSession.starts_at.asc())
        .all()
    )
    room_ids = sorted({s.room_id for s in sessions if s.room_id is not None})
    rooms_by_id = {}
    if room_ids:
        rooms_by_id = {
            r.id: r
            for r in db.query(models.Room).filter(models.Room.center_id == center_id, models.Room.id.in_(room_ids)).all()
        }
    rows = []
    level_labels = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم",
    }
    for s in sessions:
        room = rooms_by_id.get(s.room_id)
        rows.append(
            {
                "id": s.id,
                "title": s.title,
                "trainer_name": s.trainer_name,
                "level": s.level,
                "level_label": level_labels.get(s.level, s.level),
                "starts_at": s.starts_at,
                "starts_at_display": _fmt_dt_weekday_ar(s.starts_at),
                "duration_minutes": s.duration_minutes,
                "price_drop_in": s.price_drop_in,
                "room_name": room.name if room else "-",
                "spots_available": spots_available(db, s),
            }
        )

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
    recent_posts_q = (
        db.query(models.CenterPost)
        .filter(models.CenterPost.center_id == center_id, models.CenterPost.is_published.is_(True))
        .order_by(nullslast(models.CenterPost.published_at.desc()), models.CenterPost.id.desc())
        .limit(24)
        .all()
    )
    pinned_public_post = None
    if pinned_post:
        sum_full = (pinned_post.summary or "").strip()
        pinned_public_post = {
            "id": pinned_post.id,
            "title": pinned_post.title,
            "post_type": pinned_post.post_type,
            "type_label": CENTER_POST_TYPE_LABELS.get(pinned_post.post_type, pinned_post.post_type),
            "summary": sum_full,
            "summary_short": _preview_text(sum_full, 100),
            "cover_image_url": pinned_post.cover_image_url,
            "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(pinned_post.id)),
        }
    loyalty_ctx: dict = {}
    if public_user:
        loyalty_ctx = loyalty_context_for_count(
            count_confirmed_sessions_for_public_user(db, center_id, public_user),
            center=center,
        )

    public_posts_teasers: list[dict] = []
    news_ticker_items: list[dict[str, str]] = []
    if pinned_post:
        news_ticker_items.append(
            {
                "title": (pinned_post.title or "").strip(),
                "type_label": CENTER_POST_TYPE_LABELS.get(pinned_post.post_type, pinned_post.post_type),
                "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(pinned_post.id)),
            }
        )
    for p in recent_posts_q:
        if pinned_post and p.id == pinned_post.id:
            continue
        if len(public_posts_teasers) < 3:
            sum_full = (p.summary or "").strip()
            public_posts_teasers.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "post_type": p.post_type,
                    "type_label": CENTER_POST_TYPE_LABELS.get(p.post_type, p.post_type),
                    "summary": _preview_text(sum_full, 120),
                    "cover_image_url": p.cover_image_url,
                    "published_at_display": _fmt_dt(p.published_at) if p.published_at else "",
                    "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                }
            )
        if len(news_ticker_items) < 14:
            tl = (p.title or "").strip()
            if tl:
                news_ticker_items.append(
                    {
                        "title": tl,
                        "type_label": CENTER_POST_TYPE_LABELS.get(p.post_type, p.post_type),
                        "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                    }
                )
        if len(public_posts_teasers) >= 3 and len(news_ticker_items) >= 14:
            break

    num_news_on_index = (1 if pinned_public_post else 0) + len(public_posts_teasers)
    public_news_has_more = total_published_posts > num_news_on_index
    public_news_list_url = _url_with_params("/news", center_id=str(center_id))
    plan_labels = {
        "weekly": "أسبوعي",
        "monthly": "شهري",
        "yearly": "سنوي",
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "center": center,
            "center_id": center_id,
            "sessions": rows,
            "plans": [
                {
                    "id": p.id,
                    "name": p.name,
                    "plan_type": p.plan_type,
                    "plan_type_label": plan_labels.get(p.plan_type, p.plan_type),
                    "duration_days": _plan_duration_days(p.plan_type),
                    "price": p.price,
                    "session_limit": p.session_limit,
                }
                for p in plans
            ],
            "payment": payment,
            "msg": msg,
            "public_user": public_user,
            "faq_items": faq_items,
            "pinned_public_post": pinned_public_post,
            "public_posts_teasers": public_posts_teasers,
            "news_ticker_items": news_ticker_items,
            "public_news_has_more": public_news_has_more,
            "public_news_list_url": public_news_list_url,
            "loyalty_program_rows": loyalty_program_table_rows(center),
            "feedback_enabled": bool(feedback_destination_email()) and validate_mailer_settings()[0],
            **loyalty_ctx,
            **_analytics_context("index", center_id=str(center_id)),
        },
    )


@router.post("/public/feedback")
async def public_feedback_submit(
    request: Request,
    center_id: int = Form(1),
    category: str = Form(...),
    message: str = Form(...),
    contact_name: str = Form(""),
    contact_phone: str = Form(""),
    images: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    """إرسال مشكلة / شكوى / اقتراح من الواجهة العامة إلى بريد الإدارة (مع صور اختيارية)."""
    pu = _current_public_user(request, db)
    if not pu:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_auth_required"),
            status_code=303,
        )

    dest = feedback_destination_email()
    ok_cfg, _why = validate_mailer_settings()
    if not dest or not ok_cfg:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_unavailable"),
            status_code=303,
        )

    cat_key = (category or "").strip().lower()
    if cat_key not in PUBLIC_FEEDBACK_CATEGORY_LABELS:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    msg_text = (message or "").strip()
    if len(msg_text) < 3 or len(msg_text) > 8000:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )

    name_sub = (contact_name or "").strip()
    if len(name_sub) < 2 or len(name_sub) > 200:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )
    phone_sub = (contact_phone or "").strip()[:40]

    ce = (pu.email or "").strip().lower()
    if not ce or "@" not in ce or len(ce) > 254:
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )

    fb_key = _request_key(request, "public_feedback", f"{center_id}")
    if not rate_limiter.allow(fb_key, limit=5, window_seconds=3600, lockout_seconds=120, max_lockout_seconds=MAX_LOCKOUT_SECONDS):
        log_security_event("public_feedback", request, "rate_limited", email=ce or None)
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_rate_limited"),
            status_code=303,
        )

    attachments: list[tuple[str, bytes, str]] = []
    upload_list = images if images else []
    for uf in upload_list:
        if not uf.filename:
            continue
        ct = (uf.content_type or "").split(";")[0].strip().lower()
        if ct not in PUBLIC_FEEDBACK_ALLOWED_IMAGE_TYPES:
            return RedirectResponse(
                url=_url_with_params("/index", center_id=str(center_id), msg="feedback_bad_image"),
                status_code=303,
            )
        raw = await uf.read()
        if len(raw) > PUBLIC_FEEDBACK_MAX_IMAGE_BYTES:
            return RedirectResponse(
                url=_url_with_params("/index", center_id=str(center_id), msg="feedback_image_too_large"),
                status_code=303,
            )
        if len(attachments) >= PUBLIC_FEEDBACK_MAX_IMAGES:
            break
        safe_name = os.path.basename(uf.filename or "image.jpg")[:180]
        attachments.append((safe_name, raw, ct))

    app_name = os.getenv("APP_NAME", "Maestro Yoga")
    cat_label = PUBLIC_FEEDBACK_CATEGORY_LABELS[cat_key]
    ip = get_client_ip(request)
    subject = f"{app_name} — {center.name} — {cat_label}"
    body_lines = [
        f"المركز: {center.name} (center_id={center_id})",
        f"التصنيف: {cat_label}",
        f"الاسم: {name_sub}",
        f"الجوال: {phone_sub or '—'}",
        f"البريد (من حساب المستخدم): {ce}",
        "",
        "النص:",
        msg_text,
        "",
        f"عنوان IP: {ip}",
    ]
    body = "\n".join(body_lines)
    html_body = (
        f"<div dir='rtl' style='font-family:Tahoma,Arial,sans-serif;line-height:1.6'>"
        f"<p><strong>المركز:</strong> {html_escape(center.name)}</p>"
        f"<p><strong>التصنيف:</strong> {html_escape(cat_label)}</p>"
        f"<p><strong>الاسم:</strong> {html_escape(name_sub)}</p>"
        f"<p><strong>الجوال:</strong> {html_escape(phone_sub or '—')}</p>"
        f"<p><strong>البريد:</strong> {html_escape(ce)}</p>"
        f"<p><strong>النص:</strong></p><pre style='white-space:pre-wrap'>{html_escape(msg_text)}</pre>"
        f"<p><strong>IP:</strong> {html_escape(ip)}</p>"
        f"</div>"
    )

    sent_ok, send_reason = send_mail_with_attachments(
        dest,
        subject,
        body,
        html_body=html_body,
        attachments=attachments or None,
    )
    if not sent_ok:
        log_security_event(
            "public_feedback",
            request,
            "send_failed",
            email=ce or None,
            details={"reason": send_reason[:400]},
        )
        return RedirectResponse(
            url=_url_with_params("/index", center_id=str(center_id), msg="feedback_error"),
            status_code=303,
        )
    log_security_event("public_feedback", request, "success", email=ce or None)
    return RedirectResponse(
        url=_url_with_params("/index", center_id=str(center_id), msg="feedback_sent"),
        status_code=303,
    )


@router.get("/news", response_class=HTMLResponse)
def public_news_list(
    request: Request,
    center_id: int = 1,
    filter_type: str | None = Query(None, alias="type", description="تصفية حسب نوع المنشور"),
    sort: str = Query("newest", description="newest | oldest | recent"),
    db: Session = Depends(get_db),
):
    center = db.get(models.Center, center_id)
    if not center:
        ensure_demo_data(db)
        center = db.get(models.Center, center_id)
        if not center:
            center = db.query(models.Center).order_by(models.Center.id.asc()).first()
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    if center.name == DEMO_CENTER_NAME:
        ensure_demo_news_posts(db, center.id)
    _clear_center_branding_urls_if_files_missing(db, center)

    type_key = (filter_type or "").strip().lower()
    if type_key and type_key not in CENTER_POST_TYPES:
        type_key = ""
    sort_key = (sort or "newest").strip().lower()
    if sort_key not in NEWS_LIST_SORT_MODES:
        sort_key = "newest"

    q = db.query(models.CenterPost).filter(
        models.CenterPost.center_id == center_id,
        models.CenterPost.is_published.is_(True),
    )
    if type_key:
        q = q.filter(models.CenterPost.post_type == type_key)

    if sort_key == "oldest":
        q = q.order_by(
            models.CenterPost.is_pinned.desc(),
            nullslast(models.CenterPost.published_at.asc()),
            models.CenterPost.id.asc(),
        )
    elif sort_key == "recent":
        q = q.order_by(
            models.CenterPost.is_pinned.desc(),
            models.CenterPost.created_at.desc(),
            models.CenterPost.id.desc(),
        )
    else:
        q = q.order_by(
            models.CenterPost.is_pinned.desc(),
            nullslast(models.CenterPost.published_at.desc()),
            models.CenterPost.id.desc(),
        )

    posts = q.all()
    news_rows = []
    for p in posts:
        sum_full = (p.summary or "").strip()
        news_rows.append(
            {
                "title": p.title,
                "post_type": p.post_type,
                "type_label": CENTER_POST_TYPE_LABELS.get(p.post_type, p.post_type),
                "summary": _preview_text(sum_full, 180),
                "published_at_display": _fmt_dt(p.published_at) if p.published_at else "",
                "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                "cover_image_url": p.cover_image_url,
                "is_pinned": bool(p.is_pinned),
            }
        )

    post_type_filter_options = [("", "كل الأنواع")] + [(k, CENTER_POST_TYPE_LABELS[k]) for k in sorted(CENTER_POST_TYPES)]
    sort_filter_options = [
        ("newest", "الأحدث نشراً"),
        ("oldest", "الأقدم نشراً"),
        ("recent", "آخر إضافة"),
    ]

    return templates.TemplateResponse(
        request,
        "public_news_list.html",
        {
            "center": center,
            "center_id": center_id,
            "news_rows": news_rows,
            "news_type_filter": type_key,
            "news_sort": sort_key,
            "post_type_filter_options": post_type_filter_options,
            "sort_filter_options": sort_filter_options,
            "index_url": _url_with_params("/index", center_id=str(center_id)),
            **_analytics_context("public_news_list", center_id=str(center_id)),
        },
    )


@router.get("/post", response_class=HTMLResponse)
def public_post_detail(
    request: Request,
    center_id: int,
    post_id: int,
    db: Session = Depends(get_db),
):
    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    post = db.get(models.CenterPost, post_id)
    if not post or post.center_id != center_id or not post.is_published:
        raise HTTPException(status_code=404, detail="Post not found")
    _clear_center_branding_urls_if_files_missing(db, center)
    imgs = (
        db.query(models.CenterPostImage)
        .filter(models.CenterPostImage.post_id == post.id)
        .order_by(models.CenterPostImage.sort_order.asc(), models.CenterPostImage.id.asc())
        .all()
    )
    gallery = [{"id": i.id, "url": i.image_url} for i in imgs]
    public_user = _current_public_user(request, db)
    loyalty_ctx: dict = {}
    if public_user:
        loyalty_ctx = loyalty_context_for_count(
            count_confirmed_sessions_for_public_user(db, center_id, public_user),
            center=center,
        )
    return templates.TemplateResponse(
        request,
        "post_detail.html",
        {
            "center": center,
            "center_id": center_id,
            "public_user": public_user,
            **loyalty_ctx,
            "post": {
                "id": post.id,
                "title": post.title,
                "post_type": post.post_type,
                "type_label": CENTER_POST_TYPE_LABELS.get(post.post_type, post.post_type),
                "summary": post.summary or "",
                "body": post.body or "",
                "cover_image_url": post.cover_image_url,
                "published_at_display": _fmt_dt(post.published_at) if post.published_at else "",
            },
            "gallery": gallery,
            "index_url": _url_with_params("/index", center_id=str(center_id)),
            **_analytics_context("post", center_id=str(center_id), post_id=str(post_id)),
        },
    )


@router.post("/public/book")
def public_book(
    request: Request,
    center_id: int = Form(...),
    session_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    yoga_session = db.get(models.YogaSession, session_id)
    if not yoga_session or yoga_session.center_id != center_id:
        raise HTTPException(status_code=404, detail="Session not found")

    if spots_available(db, yoga_session) <= 0:
        return RedirectResponse(
            url=f"/index?center_id={center_id}&msg=full",
            status_code=303,
        )

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    duplicate = (
        db.query(models.Booking)
        .filter(
            models.Booking.session_id == session_id,
            models.Booking.client_id == client.id,
            models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .first()
    )
    if duplicate:
        return RedirectResponse(
            url=f"/index?center_id={center_id}&msg=duplicate",
            status_code=303,
        )

    booking = models.Booking(
        center_id=center_id,
        session_id=session_id,
        client_id=client.id,
        status="pending_payment",
    )
    db.add(booking)
    db.flush()

    amount = float(yoga_session.price_drop_in)
    payment_row = models.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=booking.id,
        amount=amount,
        currency="SAR",
        payment_method="public_checkout",
        status="pending",
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)

    provider = get_payment_provider()
    base = _public_base(request)

    if payment_provider_supports_hosted_checkout(provider):
        try:
            provider_result = provider.create_checkout_session(
                amount=amount,
                currency="sar",
                metadata={
                    "payment_id": str(payment_row.id),
                    "booking_id": str(booking.id),
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled",
                line_item_name=f"حجز جلسة — {yoga_session.title}"[:120],
                line_item_description=f"{center.name} · {_fmt_dt(yoga_session.starts_at)} · {yoga_session.duration_minutes} دقيقة"[
                    :500
                ],
            )
        except Exception as exc:
            booking.status = "cancelled"
            payment_row.status = "failed"
            db.commit()
            log_security_event(
                "public_book",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id, "session_id": session_id},
            )
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_error",
                status_code=303,
            )

        payment_row.provider_ref = provider_result.provider_ref
        db.commit()
        checkout_url = provider_result.checkout_url or ""
        if not checkout_url:
            booking.status = "cancelled"
            payment_row.status = "failed"
            db.commit()
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_no_url",
                status_code=303,
            )
        return RedirectResponse(url=checkout_url, status_code=303)

    provider_result = provider.charge(
        amount=amount,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client.id, "booking_id": booking.id},
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    booking.status = "confirmed"
    db.commit()

    return RedirectResponse(
        url=f"/index?center_id={center_id}&msg=paid_mock&booking_id={booking.id}",
        status_code=303,
    )


@router.post("/public/cart/checkout")
def public_cart_checkout(
    request: Request,
    center_id: int = Form(...),
    cart_json: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    try:
        raw_items = json.loads(cart_json)
    except (json.JSONDecodeError, TypeError):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
    if not isinstance(raw_items, list) or not raw_items:
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_empty", status_code=303)

    session_ids: list[int] = []
    for it in raw_items:
        if not isinstance(it, dict):
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
        if it.get("type") != "session":
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
        sid = it.get("session_id")
        if isinstance(sid, str) and sid.strip().isdigit():
            session_ids.append(int(sid.strip()))
        elif isinstance(sid, int):
            session_ids.append(sid)
    seen: set[int] = set()
    deduped: list[int] = []
    for sid in session_ids:
        if sid not in seen:
            seen.add(sid)
            deduped.append(sid)
    session_ids = deduped
    if not session_ids:
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_empty", status_code=303)
    if len(session_ids) > MAX_PUBLIC_CART_SESSIONS:
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_too_many", status_code=303)

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    bundle: list[tuple[models.Booking, models.Payment, models.YogaSession]] = []
    for session_id in session_ids:
        yoga_session = db.get(models.YogaSession, session_id)
        if not yoga_session or yoga_session.center_id != center_id:
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_invalid", status_code=303)
        if spots_available(db, yoga_session) <= 0:
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=cart_session_full", status_code=303)
        duplicate = (
            db.query(models.Booking)
            .filter(
                models.Booking.session_id == session_id,
                models.Booking.client_id == client.id,
                models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .first()
        )
        if duplicate:
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=duplicate", status_code=303)
        booking = models.Booking(
            center_id=center_id,
            session_id=session_id,
            client_id=client.id,
            status="pending_payment",
        )
        db.add(booking)
        db.flush()
        amount = float(yoga_session.price_drop_in)
        payment_row = models.Payment(
            center_id=center_id,
            client_id=client.id,
            booking_id=booking.id,
            amount=amount,
            currency="SAR",
            payment_method="public_cart_checkout",
            status="pending",
        )
        db.add(payment_row)
        db.flush()
        bundle.append((booking, payment_row, yoga_session))

    db.commit()

    provider = get_payment_provider()
    base = _public_base(request)

    if payment_provider_supports_hosted_checkout(provider):
        line_specs = [
            (
                float(ys.price_drop_in),
                f"حجز جلسة — {ys.title}"[:120],
                f"{center.name} · {_fmt_dt(ys.starts_at)} · {ys.duration_minutes} دقيقة"[:500],
            )
            for _, _, ys in bundle
        ]
        payment_ids_meta = ",".join(str(p.id) for _, p, _ in bundle)
        try:
            provider_result = provider.create_checkout_session_multi_line(
                currency="sar",
                line_specs=line_specs,
                metadata={
                    "payment_ids": payment_ids_meta,
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                    "cart": "1",
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled",
            )
        except Exception as exc:
            for bk, pay, _ in bundle:
                bk.status = "cancelled"
                pay.status = "failed"
            db.commit()
            log_security_event(
                "public_cart_checkout",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id},
            )
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_error", status_code=303)

        pref = provider_result.provider_ref
        checkout_url = provider_result.checkout_url or ""
        if not pref or not checkout_url:
            for bk, pay, _ in bundle:
                bk.status = "cancelled"
                pay.status = "failed"
            db.commit()
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_no_url", status_code=303)
        for _, pay, _ in bundle:
            pay.provider_ref = pref
        db.commit()
        return RedirectResponse(url=checkout_url, status_code=303)

    total = sum(float(ys.price_drop_in) for _, _, ys in bundle)
    provider_result = provider.charge(
        amount=total,
        currency="SAR",
        metadata={"center_id": center_id, "client_id": client.id, "cart": "1"},
    )
    pref = provider_result.provider_ref
    for bk, pay, _ in bundle:
        pay.provider_ref = pref
        if provider_result.status == "paid":
            pay.status = "paid"
            bk.status = "confirmed"
        else:
            pay.status = "failed"
            bk.status = "cancelled"
    db.commit()
    first_bid = bundle[0][0].id if bundle else ""
    return RedirectResponse(
        url=f"/index?center_id={center_id}&msg=paid_mock&booking_id={first_bid}",
        status_code=303,
    )


@router.get("/public/register", response_class=HTMLResponse)
def public_register_page(request: Request, next: str = PUBLIC_INDEX_DEFAULT_PATH):
    safe_next = _sanitize_next_url(request.query_params.get("next") or next)
    return templates.TemplateResponse(
        request,
        "public_register.html",
        {"next": safe_next, **_analytics_context("public_register")},
    )


@router.post("/public/register")
def public_register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    country_code: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    next: str = Form(PUBLIC_INDEX_DEFAULT_PATH),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    email_normalized = email.lower().strip()
    full_name_normalized = full_name.strip()
    phone_normalized = _normalize_phone_with_country(country_code, phone)
    if (
        not full_name_normalized
        or not email_normalized
        or not password.strip()
        or not phone.strip()
        or not country_code.strip()
    ):
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="required_fields", next=safe_next),
            status_code=303,
        )
    if phone_normalized is None:
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="invalid_phone", next=safe_next),
            status_code=303,
        )
    register_key = _request_key(request, "public_register", email_normalized)
    if not rate_limiter.allow(
        register_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_register", request, "rate_limited", email=email_normalized)
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="rate_limited", next=safe_next),
            status_code=303,
        )
    exists = db.query(models.PublicUser).filter(models.PublicUser.email == email_normalized).first()
    if exists and not exists.is_deleted:
        log_security_event("public_register", request, "already_exists", email=email_normalized)
        return _public_login_redirect(msg="account_exists")
    phone_exists = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.phone == phone_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    if phone_exists:
        log_security_event("public_register", request, "phone_already_exists", email=email_normalized)
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="phone_exists", next=safe_next),
            status_code=303,
        )
    if not _is_strong_public_password(password):
        log_security_event("public_register", request, "weak_password", email=email_normalized)
        return RedirectResponse(
            url=_url_with_params("/public/register", msg="weak_password", next=safe_next),
            status_code=303,
        )

    if exists and exists.is_deleted:
        user = exists
        user.full_name = full_name_normalized
        user.email = email_normalized
        user.phone = phone_normalized
        user.password_hash = hash_password(password)
        user.email_verified = not _is_email_verification_required()
        user.verification_sent_at = utcnow_naive()
        user.is_active = True
        user.is_deleted = False
        user.deleted_at = None
        status_label = "restored"
    else:
        user = models.PublicUser(
            full_name=full_name_normalized,
            email=email_normalized,
            phone=phone_normalized,
            password_hash=hash_password(password),
            email_verified=not _is_email_verification_required(),
            verification_sent_at=utcnow_naive(),
            is_active=True,
            is_deleted=False,
        )
        db.add(user)
        status_label = "created"
    db.commit()
    db.refresh(user)

    queued, mail_info = (True, "verification_bypassed")
    if _is_email_verification_required():
        queued, mail_info = _queue_verify_email_for_user(request, user, next_url=safe_next)
    if not queued:
        log_security_event(
            "public_register",
            request,
            "mail_failed",
            email=user.email,
            details={"mail_error": mail_info[:200], "state": status_label},
        )
    else:
        log_security_event(
            "public_register",
            request,
            "success",
            email=user.email,
            details={"mail_status": "queued", "state": status_label},
        )
    token = create_public_access_token(user.id)
    if _is_email_verification_required():
        next_msg = "registered" if queued else "mail_failed"
        vp_params: dict[str, str] = {"msg": next_msg, "next": safe_next}
        if not queued:
            why = public_mail_fail_why_token(mail_info)
            if why:
                vp_params["why"] = why
        response = RedirectResponse(
            url=_url_with_params("/public/verify-pending", **vp_params),
            status_code=303,
        )
    else:
        sep = "&" if "?" in safe_next else "?"
        response = RedirectResponse(url=f"{safe_next}{sep}msg=registered_no_verify", status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/public/login", response_class=HTMLResponse)
def public_login_page(request: Request, next: str = PUBLIC_INDEX_DEFAULT_PATH):
    return templates.TemplateResponse(request, "public_login.html", {"next": next, **_analytics_context("public_login")})


@router.post("/public/login")
def public_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(PUBLIC_INDEX_DEFAULT_PATH),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    email_normalized = email.lower().strip()
    login_key = _request_key(request, "public_login", email_normalized)
    if not rate_limiter.allow(
        login_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_login", request, "rate_limited", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="rate_limited")
    user = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.email == email_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        log_security_event("public_login", request, "invalid_credentials", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="invalid_credentials")
    if not user.is_active:
        log_security_event("public_login", request, "inactive", email=email_normalized)
        return _public_login_redirect(next_url=safe_next, msg="inactive")

    token = create_public_access_token(user.id)
    if _is_email_verification_required() and not user.email_verified:
        response = RedirectResponse(url=_url_with_params("/public/verify-pending", next=safe_next), status_code=303)
    else:
        response = RedirectResponse(url=safe_next, status_code=303)
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    log_security_event(
        "public_login",
        request,
        "success",
        email=user.email,
        details={"email_verified": user.email_verified},
    )
    return response


@router.get("/public/logout")
def public_logout():
    # Request object is not required for logout, so this event is not logged here.
    response = RedirectResponse(url=f"{PUBLIC_INDEX_DEFAULT_PATH}&msg=logged_out", status_code=303)
    response.delete_cookie(PUBLIC_COOKIE_NAME)
    return response


@router.get("/public/account", response_class=HTMLResponse)
def public_account_page(request: Request, next: str = PUBLIC_INDEX_DEFAULT_PATH, db: Session = Depends(get_db)):
    safe_next = _sanitize_next_url(request.query_params.get("next") or next)
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    cc, phone_local = _public_account_phone_prefill(user)
    try:
        center_id_loyalty = int(public_center_id_str_from_next(safe_next))
    except ValueError:
        center_id_loyalty = 1
    center_loyalty = db.get(models.Center, center_id_loyalty)
    loyalty_ctx = loyalty_context_for_count(
        count_confirmed_sessions_for_public_user(db, center_id_loyalty, user),
        center=center_loyalty,
    )
    return templates.TemplateResponse(
        request,
        "public_account.html",
        {
            "next": safe_next,
            "user": user,
            "country_code": cc,
            "phone_local": phone_local,
            "loyalty_program_rows": loyalty_program_table_rows(center_loyalty),
            **loyalty_ctx,
            **_analytics_context("public_account"),
        },
    )


@router.post("/public/account")
def public_account_update(
    request: Request,
    full_name: str = Form(...),
    country_code: str = Form(...),
    phone: str = Form(...),
    next: str = Form(PUBLIC_INDEX_DEFAULT_PATH),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    full_name_n = full_name.strip()
    if not full_name_n or not phone.strip() or not country_code.strip():
        return RedirectResponse(
            url=_url_with_params("/public/account", msg="required_fields", next=safe_next),
            status_code=303,
        )
    phone_n = _normalize_phone_with_country(country_code, phone)
    if phone_n is None:
        return RedirectResponse(
            url=_url_with_params("/public/account", msg="invalid_phone", next=safe_next),
            status_code=303,
        )
    other = (
        db.query(models.PublicUser)
        .filter(
            models.PublicUser.phone == phone_n,
            models.PublicUser.is_deleted.is_(False),
            models.PublicUser.id != user.id,
        )
        .first()
    )
    if other:
        log_security_event(
            "public_account_update",
            request,
            "phone_conflict",
            email=user.email,
            details={"public_user_id": user.id},
        )
        return RedirectResponse(
            url=_url_with_params("/public/account", msg="phone_exists", next=safe_next),
            status_code=303,
        )
    user.full_name = full_name_n
    user.phone = phone_n
    db.commit()
    log_security_event(
        "public_account_update",
        request,
        "success",
        email=user.email,
        details={"public_user_id": user.id},
    )
    return RedirectResponse(
        url=_url_with_params("/public/account", msg="saved", next=safe_next),
        status_code=303,
    )


@router.get("/public/verify-pending", response_class=HTMLResponse)
def public_verify_pending(request: Request, next: str = PUBLIC_INDEX_DEFAULT_PATH, db: Session = Depends(get_db)):
    safe_next = _sanitize_next_url(next)
    msg_param = (request.query_params.get("msg") or "").strip()
    vk_param = (request.query_params.get("vk") or "").strip()
    flash_user = _public_user_from_verify_flash_token(db, vk_param) if msg_param == "email_verified" else None
    user = _current_public_user(request, db)
    if msg_param == "email_verified":
        target: models.PublicUser | None = None
        if flash_user:
            target = flash_user
        elif user and user.email_verified:
            target = user
        if target:
            index_url = public_index_url_from_next(safe_next, msg="email_verified")
            fn = (target.full_name or "").strip().split()
            user_first_name = fn[0] if fn else ""
            response = templates.TemplateResponse(
                request,
                "public_verify_pending.html",
                {
                    "next": safe_next,
                    "user": target,
                    "show_dev_verify_link": False,
                    "dev_verify_url": "",
                    "show_email_verified_success": True,
                    "index_url": index_url,
                    "user_first_name": user_first_name,
                    **_analytics_context("public_verify_pending"),
                },
            )
            if (not user) or user.id != target.id:
                response.set_cookie(
                    key=PUBLIC_COOKIE_NAME,
                    value=create_public_access_token(target.id),
                    httponly=True,
                    samesite="lax",
                    secure=_cookie_secure_flag(request),
                    max_age=60 * 60 * 24 * 7,
                )
            return response
    if not user:
        return _public_login_redirect(next_url=safe_next)
    if not _is_email_verification_required():
        return RedirectResponse(url=public_index_url_from_next(safe_next), status_code=303)
    if user.email_verified:
        return RedirectResponse(url=public_index_url_from_next(safe_next), status_code=303)
    show_dev_verify_link = _is_truthy_env(os.getenv("SHOW_DEV_VERIFY_LINK"))
    dev_verify_url = _build_verify_url(request, user, next_url=safe_next) if show_dev_verify_link else ""
    return templates.TemplateResponse(
        request,
        "public_verify_pending.html",
        {
            "next": safe_next,
            "user": user,
            "show_dev_verify_link": show_dev_verify_link,
            "dev_verify_url": dev_verify_url,
            "show_email_verified_success": False,
            **_analytics_context("public_verify_pending"),
        },
    )


@router.post("/public/resend-verification")
def public_resend_verification(
    request: Request,
    next: str = Form(PUBLIC_INDEX_DEFAULT_PATH),
    db: Session = Depends(get_db),
):
    safe_next = _sanitize_next_url(next)
    if _is_ip_blocked(db, request):
        return _public_login_redirect(next_url=safe_next, msg="ip_blocked")
    resend_key = _request_key(request, "public_resend_verify")
    if not rate_limiter.allow(
        resend_key,
        limit=6,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_resend_verification", request, "rate_limited")
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="rate_limited", next=safe_next),
            status_code=303,
        )
    user = _current_public_user(request, db)
    if not user:
        return _public_login_redirect(next_url=safe_next)
    now = utcnow_naive()
    if user.verification_sent_at and (now - user.verification_sent_at).total_seconds() < 60:
        log_security_event("public_resend_verification", request, "too_soon", email=user.email)
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="resend_too_soon", next=safe_next),
            status_code=303,
        )
    user.verification_sent_at = now
    db.commit()
    queued, mail_info = _queue_verify_email_for_user(request, user, next_url=safe_next)
    if not queued:
        log_security_event(
            "public_resend_verification",
            request,
            "mail_failed",
            email=user.email,
            details={"mail_error": mail_info[:200]},
        )
        why = public_mail_fail_why_token(mail_info)
        vp = {"msg": "mail_failed", "next": safe_next}
        if why:
            vp["why"] = why
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", **vp),
            status_code=303,
        )
    log_security_event(
        "public_resend_verification",
        request,
        "success",
        email=user.email,
        details={"mail_status": "queued"},
    )
    return RedirectResponse(
        url=_url_with_params("/public/verify-pending", msg="resent", next=safe_next),
        status_code=303,
    )


@router.get("/public/verify-email")
def public_verify_email(
    request: Request,
    token: str = "",
    next: str = PUBLIC_INDEX_DEFAULT_PATH,
    db: Session = Depends(get_db),
):
    token_value = token.strip().strip("<>").strip('"').strip("'")
    safe_next = _sanitize_next_url(next)
    if not token_value:
        return RedirectResponse(url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next), status_code=303)
    try:
        payload = decode_public_email_verification_token(token_value)
    except HTTPException:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="expired_link", next=safe_next),
            status_code=303,
        )
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next),
            status_code=303,
        )
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", msg="invalid_link", next=safe_next),
            status_code=303,
        )
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    session_token = create_public_access_token(user.id)
    flash_token = create_public_email_verify_flash_token(user.id, user.email)
    response = RedirectResponse(
        url=_url_with_params("/public/verify-pending", msg="email_verified", next=safe_next, vk=flash_token),
        status_code=303,
    )
    response.set_cookie(
        key=PUBLIC_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure_flag(request),
        max_age=60 * 60 * 24 * 7,
    )
    log_security_event(
        "public_verify_email",
        request,
        "success",
        email=user.email,
        details={"public_user_id": user.id},
    )
    return response


@router.get("/public/forgot-password", response_class=HTMLResponse)
def public_forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "public_forgot_password.html", _analytics_context("public_forgot_password"))


@router.post("/public/forgot-password")
def public_forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    email_normalized = email.lower().strip()
    forgot_key = _request_key(request, "public_forgot_password", email_normalized)
    if not rate_limiter.allow(
        forgot_key,
        limit=5,
        window_seconds=300,
        lockout_seconds=600,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_forgot_password", request, "rate_limited", email=email_normalized)
        return RedirectResponse(url="/public/forgot-password?msg=rate_limited", status_code=303)

    user = (
        db.query(models.PublicUser)
        .filter(models.PublicUser.email == email_normalized, models.PublicUser.is_deleted.is_(False))
        .first()
    )
    mail_sent = False
    if user and user.is_active:
        reset_url = _build_reset_url(request, user)
        mail_sent, mail_info = queue_password_reset_email(user.email, reset_url, full_name=user.full_name)
        if not mail_sent:
            log_security_event(
                "public_forgot_password",
                request,
                "mail_failed",
                email=email_normalized,
                details={"mail_error": mail_info[:200]},
            )
    log_security_event("public_forgot_password", request, "accepted", email=email_normalized)
    # Keep response neutral, but surface delivery issue when sending fails for an existing account.
    if user and user.is_active and not mail_sent:
        why = public_mail_fail_why_token(mail_info)
        fp = {"msg": "mail_failed"}
        if why:
            fp["why"] = why
        return RedirectResponse(
            url=_url_with_params("/public/forgot-password", **fp),
            status_code=303,
        )
    return RedirectResponse(url="/public/forgot-password?msg=sent", status_code=303)


@router.get("/public/reset-password", response_class=HTMLResponse)
def public_reset_password_page(request: Request, token: str | None = None):
    raw = (token or "").strip()
    token_valid = False
    if raw:
        try:
            decode_public_password_reset_token(raw)
            token_valid = True
        except HTTPException:
            token_valid = False
    return templates.TemplateResponse(
        request,
        "public_reset_password.html",
        {
            "token": raw if token_valid else "",
            "reset_token_missing": not raw,
            "reset_token_invalid": bool(raw) and not token_valid,
            **_analytics_context("public_reset_password"),
        },
    )


@router.post("/public/reset-password")
def public_reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return _public_login_redirect(msg="ip_blocked")
    reset_key = _request_key(request, "public_reset_password")
    if not rate_limiter.allow(
        reset_key,
        limit=8,
        window_seconds=300,
        lockout_seconds=300,
        max_lockout_seconds=MAX_LOCKOUT_SECONDS,
    ):
        log_security_event("public_reset_password", request, "rate_limited")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="rate_limited"),
            status_code=303,
        )
    if not _is_strong_public_password(password):
        log_security_event("public_reset_password", request, "weak_password")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="weak_password"),
            status_code=303,
        )
    if password != confirm_password:
        log_security_event("public_reset_password", request, "password_mismatch")
        return RedirectResponse(
            url=_url_with_params("/public/reset-password", token=token, msg="password_mismatch"),
            status_code=303,
        )

    try:
        payload = decode_public_password_reset_token(token)
        user_id = int(payload.get("sub"))
    except (HTTPException, TypeError, ValueError):
        log_security_event("public_reset_password", request, "invalid_token")
        return _public_login_redirect(msg="invalid_reset_link")
    email = str(payload.get("email", "")).lower().strip()
    user = db.get(models.PublicUser, user_id)
    if not user or user.email.lower() != email or user.is_deleted:
        log_security_event("public_reset_password", request, "invalid_token")
        return _public_login_redirect(msg="invalid_reset_link")

    user.password_hash = hash_password(password)
    user.is_active = True
    db.commit()
    log_security_event("public_reset_password", request, "success", email=user.email)
    return _public_login_redirect(msg="password_reset_success")

@router.post("/public/subscribe")
def public_subscribe(
    request: Request,
    center_id: int = Form(...),
    plan_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if _is_ip_blocked(db, request):
        return RedirectResponse(url=f"/index?center_id={center_id}&msg=ip_blocked", status_code=303)
    public_user = _current_public_user(request, db)
    if not public_user:
        return _public_login_redirect(next_url=f"/index?center_id={center_id}", msg="auth_required")
    if _is_email_verification_required() and not public_user.email_verified:
        return RedirectResponse(
            url=_url_with_params("/public/verify-pending", next=f"/index?center_id={center_id}"),
            status_code=303,
        )

    center = db.get(models.Center, center_id)
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    plan = db.get(models.SubscriptionPlan, plan_id)
    if not plan or plan.center_id != center_id or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found")

    client = (
        db.query(models.Client)
        .filter(models.Client.center_id == center_id, models.Client.email == public_user.email.lower())
        .first()
    )
    if not client:
        client = models.Client(
            center_id=center_id,
            full_name=public_user.full_name,
            email=public_user.email.lower(),
            phone=public_user.phone,
        )
        db.add(client)
        db.flush()
    else:
        client.full_name = public_user.full_name
        if public_user.phone:
            client.phone = public_user.phone

    start_date = utcnow_naive()
    end_date = start_date + timedelta(days=_plan_duration_days(plan.plan_type))
    subscription = models.ClientSubscription(
        client_id=client.id,
        plan_id=plan.id,
        start_date=start_date,
        end_date=end_date,
        status="pending",
    )
    db.add(subscription)
    db.flush()

    payment_row = models.Payment(
        center_id=center_id,
        client_id=client.id,
        booking_id=None,
        amount=float(plan.price),
        currency="SAR",
        payment_method=f"subscription_{plan.plan_type}",
        status="pending",
    )
    db.add(payment_row)
    db.commit()
    db.refresh(payment_row)
    db.refresh(subscription)

    provider = get_payment_provider()
    base = _public_base(request)
    if payment_provider_supports_hosted_checkout(provider):
        try:
            provider_result = provider.create_checkout_session(
                amount=float(plan.price),
                currency="sar",
                metadata={
                    "payment_id": str(payment_row.id),
                    "subscription_id": str(subscription.id),
                    "center_id": str(center_id),
                    "client_id": str(client.id),
                    "plan_id": str(plan.id),
                },
                success_url=f"{base}/index?center_id={center_id}&payment=success&msg=subscribed",
                cancel_url=f"{base}/index?center_id={center_id}&payment=cancelled&msg=subscription_cancelled",
                line_item_name=f"اشتراك — {plan.name}"[:120],
                line_item_description=f"{center.name} · باقة {plan.plan_type}"[:500],
            )
        except Exception as exc:
            payment_row.status = "failed"
            subscription.status = "cancelled"
            db.commit()
            log_security_event(
                "public_subscribe",
                request,
                "stripe_error",
                details={"error": str(exc)[:200], "center_id": center_id, "plan_id": plan_id},
            )
            return RedirectResponse(
                url=f"/index?center_id={center_id}&msg=stripe_error",
                status_code=303,
            )

        payment_row.provider_ref = provider_result.provider_ref
        db.commit()
        checkout_url = provider_result.checkout_url or ""
        if not checkout_url:
            payment_row.status = "failed"
            subscription.status = "cancelled"
            db.commit()
            return RedirectResponse(url=f"/index?center_id={center_id}&msg=stripe_no_url", status_code=303)
        return RedirectResponse(url=checkout_url, status_code=303)

    provider_result = provider.charge(
        amount=float(plan.price),
        currency="SAR",
        metadata={
            "center_id": center_id,
            "client_id": client.id,
            "plan_id": plan.id,
            "subscription_id": subscription.id,
        },
    )
    payment_row.provider_ref = provider_result.provider_ref
    payment_row.status = provider_result.status
    subscription.status = "active" if provider_result.status == "paid" else "cancelled"
    db.commit()
    return RedirectResponse(url=f"/index?center_id={center_id}&msg=subscribed_mock", status_code=303)

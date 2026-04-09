"""Public content: version, feedback, news list, post detail."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_public_browse_routes(router: APIRouter) -> None:
    """Content version, feedback, news list, post detail."""

    @router.get("/public/content-version")
    def public_content_version(center_id: int = 1, db: _s.Session = _s.Depends(_s.get_db)):
        return {"center_id": center_id, "version": _s.compute_public_center_content_version(db, center_id)}
    
    
    @router.post("/public/feedback")
    async def public_feedback_submit(
        request: _s.Request,
        center_id: int = _s.Form(1),
        category: str = _s.Form(...),
        message: str = _s.Form(...),
        contact_name: str = _s.Form(""),
        contact_phone: str = _s.Form(""),
        images: list[_s.UploadFile] | None = _s.File(None),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        """إرسال مشكلة / شكوى / اقتراح من الواجهة العامة إلى بريد الإدارة (مع صور اختيارية)."""
        pu = _s._current_public_user(request, db)
        if not pu:
            return _s.redirect_public_index_with_params(center_id=center_id, msg="feedback_auth_required")
    
        dest = _s.feedback_destination_email()
        ok_cfg, _why = _s.validate_mailer_settings()
        if not dest or not ok_cfg:
            return _s.redirect_public_index_with_params(center_id=center_id, msg="feedback_unavailable")
    
        center = _s.get_seeded_center_or_404(db, center_id)
        app_name = _s.os.getenv("APP_NAME", "Maestro Yoga")
        prepared, prepare_error = await _s.prepare_feedback_submission(
            request=request,
            center_id=center_id,
            center_name=center.name,
            category=category,
            message=message,
            contact_name=contact_name,
            contact_phone=contact_phone,
            account_email=pu.email,
            images=images,
            category_labels=_s.PUBLIC_FEEDBACK_CATEGORY_LABELS,
            allowed_image_types=_s.PUBLIC_FEEDBACK_ALLOWED_IMAGE_TYPES,
            max_image_bytes=_s.PUBLIC_FEEDBACK_MAX_IMAGE_BYTES,
            max_images=_s.PUBLIC_FEEDBACK_MAX_IMAGES,
            max_lockout_seconds=_s.MAX_LOCKOUT_SECONDS,
            request_key_fn=_s._request_key,
            allow_fn=_s.rate_limiter.allow,
            log_security_event_fn=_s.log_security_event,
            client_ip_fn=_s.get_client_ip,
            app_name=app_name,
            is_valid_message_fn=_s.is_valid_feedback_message,
            is_valid_contact_name_fn=_s.is_valid_feedback_contact_name,
            is_valid_email_fn=_s.is_valid_feedback_email,
        )
        if prepare_error:
            return _s.redirect_public_index_with_params(center_id=center_id, msg=prepare_error)
        assert prepared is not None
    
        sent_ok, send_reason = _s.send_mail_with_attachments(
            dest,
            prepared["subject"],
            prepared["body"],
            html_body=prepared["html_body"],
            attachments=prepared["attachments"] or None,
        )
        result_msg = _s.feedback_send_result_message(
            sent_ok=sent_ok,
            send_reason=send_reason,
            request=request,
            email=prepared["email"],
            log_security_event_fn=_s.log_security_event,
        )
        return _s.redirect_public_index_with_params(center_id=center_id, msg=result_msg)
    
    
    @router.get("/news", response_class=_s.HTMLResponse)
    def public_news_list(
        request: _s.Request,
        center_id: int = 1,
        filter_type: str | None = _s.Query(None, alias="type", description="تصفية حسب نوع المنشور"),
        sort: str = _s.Query("newest", description="newest | oldest | recent"),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        center = _s.resolve_public_center_or_404(db, center_id)
        if center.name == _s.DEMO_CENTER_NAME:
            _s.ensure_demo_news_posts(db, center.id)
        _s._clear_center_branding_urls_if_files_missing(db, center)
    
        type_key = (filter_type or "").strip().lower()
        if type_key and type_key not in _s.CENTER_POST_TYPES:
            type_key = ""
        sort_key = (sort or "newest").strip().lower()
        if sort_key not in _s.NEWS_LIST_SORT_MODES:
            sort_key = "newest"
    
        q = db.query(_s.models.CenterPost).filter(
            _s.models.CenterPost.center_id == center.id,
            _s.models.CenterPost.is_published.is_(True),
        )
        q = _s.apply_public_news_filters_and_sort(
            q,
            model=_s.models.CenterPost,
            type_key=type_key,
            sort_key=sort_key,
        )
    
        posts = q.all()
        news_rows = _s.build_public_news_list_rows(posts=posts, center_id=center.id, type_labels=_s.CENTER_POST_TYPE_LABELS)
    
        post_type_filter_options, sort_filter_options = _s.build_public_news_filter_options(
            post_types=_s.CENTER_POST_TYPES,
            type_labels=_s.CENTER_POST_TYPE_LABELS,
            sort_modes=_s.NEWS_LIST_SORT_MODES,
        )
    
        return _s.templates.TemplateResponse(
            request,
            "public_news_list.html",
            {
                "center": center,
                "center_id": center.id,
                "news_rows": news_rows,
                "news_type_filter": type_key,
                "news_sort": sort_key,
                "post_type_filter_options": post_type_filter_options,
                "sort_filter_options": sort_filter_options,
                "index_url": _s._url_with_params("/index", center_id=str(center.id)),
                **_s._analytics_context("public_news_list", center_id=str(center.id)),
            },
        )
    
    
    @router.get("/post", response_class=_s.HTMLResponse)
    def public_post_detail(
        request: _s.Request,
        center_id: int,
        post_id: int,
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        center = _s.get_center_or_404(db, center_id)
        post = db.get(_s.models.CenterPost, post_id)
        if not post or post.center_id != center_id or not post.is_published:
            raise _s.HTTPException(status_code=404, detail="Post not found")
        _s._clear_center_branding_urls_if_files_missing(db, center)
        imgs = (
            db.query(_s.models.CenterPostImage)
            .filter(_s.models.CenterPostImage.post_id == post.id)
            .order_by(_s.models.CenterPostImage.sort_order.asc(), _s.models.CenterPostImage.id.asc())
            .all()
        )
        gallery = [{"id": i.id, "url": i.image_url} for i in imgs]
        public_user = _s._current_public_user(request, db)
        loyalty_ctx = _s.build_public_loyalty_context(db, center_id, public_user, center=center)
        return _s.templates.TemplateResponse(
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
                    "type_label": _s.CENTER_POST_TYPE_LABELS.get(post.post_type, post.post_type),
                    "summary": post.summary or "",
                    "body": post.body or "",
                    "cover_image_url": post.cover_image_url,
                    "published_at_display": _s._fmt_dt(post.published_at) if post.published_at else "",
                },
                "gallery": gallery,
                "index_url": _s._url_with_params("/index", center_id=str(center_id)),
                **_s._analytics_context("post", center_id=str(center_id), post_id=str(post_id)),
            },
        )
    
    

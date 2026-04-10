"""Public news list and center post detail pages."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_public_browse_news_routes(router: APIRouter) -> None:
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

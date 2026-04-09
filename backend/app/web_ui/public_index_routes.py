"""Public landing page (GET /index)."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_public_index_routes(router: APIRouter) -> None:
    """GET /index (landing)."""

    @router.get("/index", response_class=_s.HTMLResponse)
    def public_index(
        request: _s.Request,
        center_id: int | None = _s.Query(
            default=None,
            description="معرّف المركز. عند عدم الإرسال يحاول النظام اختيار مركز مناسب تلقائياً.",
        ),
        payment: str | None = None,
        msg: str | None = None,
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        public_user = _s._current_public_user(request, db)
        center = _s.resolve_public_center_or_404(db, center_id)
    
        if center.name == _s.DEMO_CENTER_NAME:
            _s.ensure_demo_news_posts(db, center.id)
    
        _s._clear_center_branding_urls_if_files_missing(db, center)
    
        sessions = (
            db.query(_s.models.YogaSession)
            .filter(_s.models.YogaSession.center_id == center.id)
            .order_by(_s.models.YogaSession.starts_at.asc())
            .all()
        )
        room_ids = sorted({s.room_id for s in sessions if s.room_id is not None})
        rooms_by_id = {}
        if room_ids:
            rooms_by_id = {
                r.id: r
                for r in db.query(_s.models.Room).filter(_s.models.Room.center_id == center.id, _s.models.Room.id.in_(room_ids)).all()
            }
        spots_by_session = _s._spots_available_map(db, center.id, [int(s.id) for s in sessions])
        rows = _s.build_public_session_rows(sessions, rooms_by_id, spots_by_session)
    
        index_data = _s.load_public_index_data(db, center.id)
        plans = index_data["plans"]
        faq_items = index_data["faq_items"]
        pinned_post = index_data["pinned_post"]
        total_published_posts = index_data["total_published_posts"]
        recent_posts_q = index_data["recent_posts"]
        pinned_public_post, public_posts_teasers, news_ticker_items = _s.build_public_posts_blocks(
            pinned_post=pinned_post,
            recent_posts=recent_posts_q,
            center_id=center.id,
            type_labels=_s.CENTER_POST_TYPE_LABELS,
        )
        loyalty_ctx = _s.build_public_loyalty_context(db, center.id, public_user, center=center)
    
        public_news_meta = _s.build_public_news_index_meta(
            center_id=center.id,
            total_published_posts=total_published_posts,
            pinned_public_post=pinned_public_post,
            public_posts_teasers=public_posts_teasers,
            url_with_params_fn=_s._url_with_params,
        )
        plan_labels = _s.default_plan_labels()
    
        index_page = _s.merge_index_page_config(center)
        idx_refund_p1 = _s._index_refund_p1_rendered(str(index_page.get("refund", {}).get("p1", "")), center.name)
    
        context = _s.build_public_index_template_context(
            request=request,
            center=center,
            rows=rows,
            plans=plans,
            payment=payment,
            msg=msg,
            public_user=public_user,
            faq_items=faq_items,
            pinned_public_post=pinned_public_post,
            public_posts_teasers=public_posts_teasers,
            news_ticker_items=news_ticker_items,
            public_news_meta=public_news_meta,
            plan_rows=_s.build_public_plan_rows(plans, plan_labels=plan_labels),
            index_page=index_page,
            index_refund_p1_html=idx_refund_p1,
            index_seo_title=_s._index_seo_title(center),
            index_meta_description=_s._index_meta_description(center, len(rows), len(plans)),
            index_preconnect_origins_fn=_s.index_preconnect_origins,
            loyalty_program_rows_fn=_s.loyalty_program_table_rows,
            feedback_enabled=bool(_s.feedback_destination_email()) and _s.validate_mailer_settings()[0],
            public_content_version=_s.compute_public_center_content_version(db, center.id),
            loyalty_ctx=loyalty_ctx,
            analytics_ctx=_s._analytics_context("index", center_id=str(center.id)),
        )
        return _s.templates.TemplateResponse(request, "index.html", context)
    
    

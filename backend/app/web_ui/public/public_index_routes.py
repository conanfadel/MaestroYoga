"""Public landing page (GET /index)."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter

from .. import impl_state as _s

# Paymob يُلحق حقول المعاملة (hmac، pan، …) بـ success_url — نُعيد التوجيه لرابط نظيف.
_INDEX_QUERY_KEEP = ("center_id", "payment", "msg", "session_id")


def _maybe_redirect_clean_index_query(request: _s.Request) -> _s.RedirectResponse | None:
    qp = request.query_params
    if not qp:
        return None
    if set(qp.keys()) <= set(_INDEX_QUERY_KEEP):
        return None
    if not (qp.get("payment") or qp.get("msg")):
        return None
    pairs: list[tuple[str, str]] = []
    for name in _INDEX_QUERY_KEEP:
        v = qp.get(name)
        if v is not None and str(v).strip() != "":
            pairs.append((name, str(v).strip()))
    if not pairs:
        return None
    return _s.RedirectResponse(url="/index?" + urlencode(pairs), status_code=303)


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
        early = _maybe_redirect_clean_index_query(request)
        if early is not None:
            return early

        public_user = _s._current_public_user(request, db)
        center = _s.resolve_public_center_or_404(db, center_id)
    
        if center.name == _s.DEMO_CENTER_NAME:
            _s.ensure_demo_news_posts(db, center.id)
    
        _s._clear_center_branding_urls_if_files_missing(db, center)
    
        now_na = _s.utcnow_naive()
        lb = _s.public_schedule_query_lower_bound_starts_at(now=now_na)
        sessions = (
            db.query(_s.models.YogaSession)
            .filter(
                _s.models.YogaSession.center_id == center.id,
                _s.models.YogaSession.starts_at >= lb,
            )
            .order_by(_s.models.YogaSession.starts_at.asc())
            .all()
        )
        sessions = _s.filter_sessions_for_public_index(sessions, now=now_na)
        room_ids = sorted({s.room_id for s in sessions if s.room_id is not None})
        rooms_by_id = {}
        if room_ids:
            rooms_by_id = {
                r.id: r
                for r in db.query(_s.models.Room).filter(_s.models.Room.center_id == center.id, _s.models.Room.id.in_(room_ids)).all()
            }
        spots_by_session = _s._spots_available_map(db, center.id, [int(s.id) for s in sessions])
        plan_labels = _s.default_plan_labels()
        subscription_ctx = _s.build_public_active_subscription_context(
            db, center.id, public_user, plan_labels
        )
        plan_booked_session_ids: set[int] = set()
        if public_user and sessions:
            email = (getattr(public_user, "email", None) or "").strip().lower()
            if email:
                client = (
                    db.query(_s.models.Client)
                    .filter(
                        _s.models.Client.center_id == center.id,
                        _s.models.Client.email == email,
                    )
                    .first()
                )
                if client:
                    plan_booked_session_ids = _s.session_ids_booked_via_plan_for_client(
                        db,
                        center_id=center.id,
                        client_id=client.id,
                        session_ids=[int(s.id) for s in sessions],
                    )
        rows = _s.build_public_session_rows(
            sessions,
            rooms_by_id,
            spots_by_session,
            plan_session_booking_enabled=bool(subscription_ctx.get("public_sub_plan_slot_booking")),
            plan_booked_session_ids=plan_booked_session_ids,
        )

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
            subscription_ctx=subscription_ctx,
            analytics_ctx=_s._analytics_context("index", center_id=str(center.id)),
            index_hero_app_name=_s.os.getenv("APP_NAME", "Maestro Yoga").strip() or "Maestro Yoga",
        )
        return _s.templates.TemplateResponse(request, "index.html", context)
    
    

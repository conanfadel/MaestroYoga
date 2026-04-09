"""Center loyalty, branding, index page config, posts."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_center_routes(router: APIRouter) -> None:
    """Center settings and posts."""

    def _optional_non_negative_int_form(raw: str) -> int | None:
        s = (raw or "").strip()
        if not s:
            return None
        try:
            v = int(s)
        except ValueError:
            raise ValueError("nan")
        if v < 0:
            raise ValueError("neg")
        return v
    
    
    @router.post("/admin/center/loyalty")
    def admin_center_loyalty(
        request: _s.Request,
        loyalty_bronze_min: str = _s.Form(""),
        loyalty_silver_min: str = _s.Form(""),
        loyalty_gold_min: str = _s.Form(""),
        loyalty_label_bronze: str = _s.Form(""),
        loyalty_label_silver: str = _s.Form(""),
        loyalty_label_gold: str = _s.Form(""),
        loyalty_reward_bronze: str = _s.Form(""),
        loyalty_reward_silver: str = _s.Form(""),
        loyalty_reward_gold: str = _s.Form(""),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("loyalty.manage")),
    ):
        cid = _s.require_user_center_id(user)
        center = db.get(_s.models.Center, cid)
        if not center:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, scroll_y, return_section)
        try:
            pb = _optional_non_negative_int_form(loyalty_bronze_min)
            ps = _optional_non_negative_int_form(loyalty_silver_min)
            pg = _optional_non_negative_int_form(loyalty_gold_min)
        except ValueError:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_LOYALTY_BAD_NUMBER, scroll_y, return_section)
    
        prospective = _s.models.Center()
        prospective.loyalty_bronze_min = pb
        prospective.loyalty_silver_min = ps
        prospective.loyalty_gold_min = pg
        b, s, g = _s.effective_loyalty_thresholds(prospective)
        err = _s.validate_loyalty_threshold_triple(b, s, g)
        if err:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_LOYALTY_INVALID, scroll_y, return_section)
    
        def _lbl(x: str) -> str | None:
            t = (x or "").strip()[:64]
            return t or None
    
        def _reward(x: str) -> str | None:
            t = (x or "").strip()[:_s.LOYALTY_REWARD_MAX_LEN]
            return t or None
    
        center.loyalty_bronze_min = pb
        center.loyalty_silver_min = ps
        center.loyalty_gold_min = pg
        center.loyalty_label_bronze = _lbl(loyalty_label_bronze)
        center.loyalty_label_silver = _lbl(loyalty_label_silver)
        center.loyalty_label_gold = _lbl(loyalty_label_gold)
        center.loyalty_reward_bronze = _reward(loyalty_reward_bronze)
        center.loyalty_reward_silver = _reward(loyalty_reward_silver)
        center.loyalty_reward_gold = _reward(loyalty_reward_gold)
        db.commit()
        _s.log_security_event(
            "admin_center_loyalty",
            request,
            "success",
            email=user.email,
            details={"center_id": cid, "thresholds": [b, s, g]},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_CENTER_LOYALTY_SAVED, scroll_y, return_section)
    
    
    @router.post("/admin/center/branding")
    async def admin_center_branding(
        brand_tagline: str = _s.Form(""),
        remove_logo: str = _s.Form(""),
        remove_hero: str = _s.Form(""),
        restore_hero_stock: str = _s.Form(""),
        hero_gradient_only: str = _s.Form(""),
        logo: _s.UploadFile | None = _s.File(default=None),
        hero: _s.UploadFile | None = _s.File(default=None),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("center.settings.edit")),
    ):
        cid = _s.require_user_center_id(user)
        center = db.get(_s.models.Center, cid)
        if not center:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, scroll_y, return_section)
        had_custom_hero = bool(center.hero_image_url)
    
        logo_raw = (logo.filename or "").strip() if logo else ""
        logo_ext: str | None = None
        logo_bytes: bytes | None = None
        if logo and logo_raw:
            ext = logo_raw.rsplit(".", 1)[-1].lower() if "." in logo_raw else ""
            if ext not in _s.CENTER_LOGO_ALLOWED_EXT:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
            body = await logo.read()
            if not body or len(body) > _s.CENTER_LOGO_MAX_BYTES:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
            logo_ext = ext
            logo_bytes = body
    
        hero_raw = (hero.filename or "").strip() if hero else ""
        hero_ext: str | None = None
        hero_bytes: bytes | None = None
        if hero and hero_raw:
            ext = hero_raw.rsplit(".", 1)[-1].lower() if "." in hero_raw else ""
            if ext not in _s.CENTER_LOGO_ALLOWED_EXT:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
            body = await hero.read()
            if not body or len(body) > _s.CENTER_LOGO_MAX_BYTES:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_BAD_FILE, scroll_y, return_section)
            hero_ext = ext
            hero_bytes = body
    
        tag = brand_tagline.strip()[:500]
        center.brand_tagline = tag if tag else None
    
        remove = _s._is_truthy_env(remove_logo)
        remove_h = _s._is_truthy_env(remove_hero)
        restore_stock = _s._is_truthy_env(restore_hero_stock)
        gradient_only = _s._is_truthy_env(hero_gradient_only)
    
        if logo_ext is not None and logo_bytes is not None:
            _s.CENTER_LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            _s._unlink_center_uploads(f"center_{cid}.*")
            dest = _s.CENTER_LOGO_UPLOAD_DIR / f"center_{cid}.{logo_ext}"
            dest.write_bytes(logo_bytes)
            center.logo_url = f"/static/uploads/centers/center_{cid}.{logo_ext}"
        elif remove:
            _s._unlink_center_uploads(f"center_{cid}.*")
            center.logo_url = None
    
        if restore_stock:
            _s._unlink_center_uploads(f"center_{cid}_hero.*")
            center.hero_image_url = None
            center.hero_show_stock_photo = True
        elif hero_ext is not None and hero_bytes is not None:
            _s.CENTER_LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            _s._unlink_center_uploads(f"center_{cid}_hero.*")
            dest = _s.CENTER_LOGO_UPLOAD_DIR / f"center_{cid}_hero.{hero_ext}"
            dest.write_bytes(hero_bytes)
            center.hero_image_url = f"/static/uploads/centers/center_{cid}_hero.{hero_ext}"
            center.hero_show_stock_photo = False
        elif remove_h:
            _s._unlink_center_uploads(f"center_{cid}_hero.*")
            center.hero_image_url = None
            center.hero_show_stock_photo = False
        elif gradient_only and not had_custom_hero:
            center.hero_show_stock_photo = False
    
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_UPDATED, scroll_y, return_section)
    
    
    @router.post("/admin/center/index-page")
    async def admin_center_index_page_save(
        request: _s.Request,
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.index")),
    ):
        cid = _s.require_user_center_id(user)
        center = db.get(_s.models.Center, cid)
        if not center:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_BRANDING_CENTER_MISSING, None, "section-index-page")
    
        form = await request.form()
        scroll_y = _s._form_str_index(form, "scroll_y", 32)
        return_section = _s._form_str_index(form, "return_section", 96)
    
        name = _s._form_str_index(form, "center_name", 200)
        city_raw = _s._form_str_index(form, "city", 120)
        if not name:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_INDEX_NAME_INVALID, scroll_y, return_section or "section-index-page")
    
        taken = (
            db.query(_s.models.Center)
            .filter(_s.models.Center.name == name, _s.models.Center.id != cid)
            .first()
        )
        if taken:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_INDEX_NAME_TAKEN, scroll_y, return_section or "section-index-page")
    
        reset_defaults = _s._is_truthy_env(_s._form_str_index(form, "reset_index_defaults", 8))
        if reset_defaults:
            center.index_config_json = None
            center.name = name
            center.city = city_raw or None
            db.commit()
            _s.log_security_event(
                "admin_center_index_page",
                request,
                "reset_defaults",
                email=user.email,
                details={"center_id": cid},
            )
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_INDEX_SAVED, scroll_y, return_section or "section-index-page")
    
        cfg = _s._index_config_build_from_form(form)
        cfg = _s._deep_merge_index_defaults(_s._default_index_page_config(), cfg)
        blob = _s.json.dumps(cfg, ensure_ascii=False)
        if len(blob) > _s.INDEX_PAGE_MAX_JSON_CHARS:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_INDEX_TOO_LARGE, scroll_y, return_section or "section-index-page")
    
        center.index_config_json = blob
        center.name = name
        center.city = city_raw or None
        db.commit()
        _s.log_security_event(
            "admin_center_index_page",
            request,
            "success",
            email=user.email,
            details={"center_id": cid},
        )
        return _s._admin_redirect(_s.ADMIN_MSG_CENTER_INDEX_SAVED, scroll_y, return_section or "section-index-page")
    
    
    @router.post("/admin/center/posts/save")
    async def admin_save_center_post(
        request: _s.Request,
        title: str = _s.Form(...),
        post_type: str = _s.Form(...),
        summary: str = _s.Form(""),
        body: str = _s.Form(""),
        post_id: str = _s.Form(""),
        is_pinned: str = _s.Form(""),
        is_published: str = _s.Form(""),
        remove_cover: str = _s.Form(""),
        remove_image_ids: str = _s.Form(""),
        cover_remote_url: str = _s.Form(""),
        gallery_remote_urls: str = _s.Form(""),
        cover: _s.UploadFile | None = _s.File(None),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.posts")),
    ):
        cid = _s.require_user_center_id(user)
        ptype = (post_type or "").strip().lower()
        if ptype not in _s.CENTER_POST_TYPES:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        ttl = (title or "").strip()
        if not ttl or len(ttl) > 220:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
        summ = (summary or "").strip()[:600]
        bod = (body or "").strip()
        if len(bod) > _s.CENTER_POST_MAX_BODY_CHARS:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
    
        pid = 0
        if (post_id or "").strip().isdigit():
            pid = int(post_id.strip())
        row: _s.models.CenterPost | None = None
        if pid:
            row = db.get(_s.models.CenterPost, pid)
            if not row or row.center_id != cid:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_NOT_FOUND, scroll_y, return_section)
        else:
            row = _s.models.CenterPost(center_id=cid, post_type=ptype, title=ttl)
            db.add(row)
            db.flush()
    
        row.post_type = ptype
        row.title = ttl
        row.summary = summ if summ else None
        row.body = bod if bod else None
        row.is_pinned = _s._is_truthy_env(is_pinned)
        row.is_published = _s._is_truthy_env(is_published)
        if row.is_published and row.published_at is None:
            row.published_at = _s.utcnow_naive()
        row.updated_at = _s.utcnow_naive()
    
        if row.is_pinned:
            db.query(_s.models.CenterPost).filter(
                _s.models.CenterPost.center_id == cid,
                _s.models.CenterPost.id != row.id,
            ).update({_s.models.CenterPost.is_pinned: False})
    
        if _s._is_truthy_env(remove_cover) and row.cover_image_url:
            _s._unlink_static_url_file(row.cover_image_url)
            row.cover_image_url = None
    
        cover_raw = (cover.filename or "").strip() if cover else ""
        if cover and cover_raw:
            ext = cover_raw.rsplit(".", 1)[-1].lower() if "." in cover_raw else ""
            if ext not in _s.CENTER_LOGO_ALLOWED_EXT:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
            cbody = await cover.read()
            if not cbody or len(cbody) > _s.CENTER_LOGO_MAX_BYTES:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
            if row.cover_image_url:
                _s._unlink_static_url_file(row.cover_image_url)
            _s.CENTER_POST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            dest = _s.CENTER_POST_UPLOAD_DIR / f"center_{cid}_post_{row.id}_cover.{ext}"
            dest.write_bytes(cbody)
            row.cover_image_url = f"/static/uploads/centers/posts/{dest.name}"
    
        cover_remote_raw = (cover_remote_url or "").strip()
        if cover_remote_raw and not (cover and cover_raw):
            sanitized_remote = _s._sanitize_center_post_remote_image_url(cover_remote_raw)
            if not sanitized_remote:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
            if row.cover_image_url and row.cover_image_url != sanitized_remote:
                _s._unlink_static_url_file(row.cover_image_url)
            row.cover_image_url = sanitized_remote
    
        for part in (remove_image_ids or "").replace(" ", "").split(","):
            if not part.isdigit():
                continue
            img_id = int(part)
            img_row = db.get(_s.models.CenterPostImage, img_id)
            if not img_row or img_row.post_id != row.id:
                continue
            _s._unlink_static_url_file(img_row.image_url)
            db.delete(img_row)
    
        form = await request.form()
        gallery_files = [
            f
            for f in form.getlist("gallery")
            if hasattr(f, "filename") and (getattr(f, "filename", None) or "").strip()
        ]
        current_n = (
            db.query(_s.models.CenterPostImage)
            .filter(_s.models.CenterPostImage.post_id == row.id)
            .count()
        )
        max_sort = (
            db.query(_s.func.coalesce(_s.func.max(_s.models.CenterPostImage.sort_order), 0))
            .filter(_s.models.CenterPostImage.post_id == row.id)
            .scalar()
        )
        next_order = int(max_sort or 0)
    
        for gf in gallery_files:
            if current_n >= _s.CENTER_POST_MAX_GALLERY:
                break
            gname = (gf.filename or "").strip()
            ext = gname.rsplit(".", 1)[-1].lower() if "." in gname else ""
            if ext not in _s.CENTER_LOGO_ALLOWED_EXT:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
            gbody = await gf.read()
            if not gbody or len(gbody) > _s.CENTER_LOGO_MAX_BYTES:
                return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_INVALID, scroll_y, return_section)
            next_order += 1
            _s.CENTER_POST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            dest = _s.CENTER_POST_UPLOAD_DIR / f"center_{cid}_post_{row.id}_gallery_{next_order}_{_s.utcnow_naive().timestamp():.0f}.{ext}"
            dest.write_bytes(gbody)
            db.add(
                _s.models.CenterPostImage(
                    post_id=row.id,
                    image_url=f"/static/uploads/centers/posts/{dest.name}",
                    sort_order=next_order,
                )
            )
            current_n += 1
    
        for remote_g in _s._parse_center_post_gallery_remote_urls(gallery_remote_urls):
            if current_n >= _s.CENTER_POST_MAX_GALLERY:
                break
            next_order += 1
            db.add(
                _s.models.CenterPostImage(
                    post_id=row.id,
                    image_url=remote_g,
                    sort_order=next_order,
                )
            )
            current_n += 1
    
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_SAVED, scroll_y, return_section)
    
    
    @router.post("/admin/center/posts/delete")
    def admin_delete_center_post(
        post_id: int = _s.Form(...),
        scroll_y: str = _s.Form(default=""),
        return_section: str = _s.Form(""),
        db: _s.Session = _s.Depends(_s.get_db),
        user: _s.models.User = _s.Depends(_s.require_permissions_cookie_or_bearer("content.posts")),
    ):
        cid = _s.require_user_center_id(user)
        row = db.get(_s.models.CenterPost, post_id)
        if not row or row.center_id != cid:
            return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_NOT_FOUND, scroll_y, return_section)
        _s._delete_center_post_disk_files(cid, row.id)
        db.delete(row)
        db.commit()
        return _s._admin_redirect(_s.ADMIN_MSG_CENTER_POST_DELETED, scroll_y, return_section)

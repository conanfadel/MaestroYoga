"""Admin center: loyalty tiers and branding (logo, hero, tagline)."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


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


def register_admin_center_loyalty_branding_routes(router: APIRouter) -> None:
    """Loyalty thresholds/labels and center branding uploads."""

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

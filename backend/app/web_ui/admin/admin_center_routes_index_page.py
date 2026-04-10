"""Admin center: public index page JSON config and center name/city."""

from __future__ import annotations

from fastapi import APIRouter

from .. import impl_state as _s


def register_admin_center_index_page_routes(router: APIRouter) -> None:
    """Save index page configuration and center display fields."""

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

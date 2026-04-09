"""Admin center: news/events posts CRUD (save + delete)."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_admin_center_posts_routes(router: APIRouter) -> None:
    """Create/update/delete center posts with cover and gallery."""

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

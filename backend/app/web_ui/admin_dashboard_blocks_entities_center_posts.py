"""Center posts admin listing and edit payload for the admin dashboard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks_pagination import normalize_admin_list_page


@dataclass(frozen=True)
class CenterPostsBundle:
    center_post_admin_rows: list[dict[str, Any]]
    editing_post: dict[str, Any] | None
    center_post_type_choices: list[dict[str, str]]
    safe_post_edit: int
    safe_center_posts_page: int
    center_posts_total: int
    center_posts_total_pages: int
    center_posts_page_size: int


def load_center_posts_admin_section(
    db: _s.Session,
    cid: int,
    center_posts_page: int,
    post_edit: int,
    post_edit_url: Callable[[int], str],
) -> CenterPostsBundle:
    safe_post_edit = max(0, int(post_edit or 0))
    center_posts_page_size = _s.ADMIN_CENTER_POSTS_PAGE_SIZE
    center_posts_base_query = (
        db.query(_s.models.CenterPost)
        .filter(_s.models.CenterPost.center_id == cid)
        .order_by(_s.models.CenterPost.updated_at.desc())
    )
    center_posts_total = center_posts_base_query.order_by(None).count()
    safe_center_posts_page, center_posts_total_pages, center_posts_offset = normalize_admin_list_page(
        center_posts_page,
        center_posts_total,
        center_posts_page_size,
    )
    center_posts_all = (
        center_posts_base_query.offset(center_posts_offset).limit(center_posts_page_size).all()
    )
    center_post_ids_page = [int(cp.id) for cp in center_posts_all]
    center_post_gallery_counts = {
        int(pid): int(cnt)
        for pid, cnt in (
            db.query(_s.models.CenterPostImage.post_id, _s.func.count(_s.models.CenterPostImage.id))
            .filter(_s.models.CenterPostImage.post_id.in_(center_post_ids_page))
            .group_by(_s.models.CenterPostImage.post_id)
            .all()
        )
    } if center_post_ids_page else {}

    center_post_admin_rows: list[dict[str, Any]] = []
    for cp in center_posts_all:
        center_post_admin_rows.append(
            {
                "id": cp.id,
                "title": cp.title,
                "post_type": cp.post_type,
                "type_label": _s.CENTER_POST_TYPE_LABELS.get(cp.post_type, cp.post_type),
                "is_published": cp.is_published,
                "is_pinned": cp.is_pinned,
                "updated_display": _s._fmt_dt(cp.updated_at),
                "gallery_count": center_post_gallery_counts.get(int(cp.id), 0),
                "public_url": _s._url_with_params("/post", center_id=str(cid), post_id=str(cp.id))
                if cp.is_published
                else "",
                "edit_url": post_edit_url(cp.id),
            }
        )

    editing_post: dict[str, Any] | None = None
    if safe_post_edit:
        ep = db.get(_s.models.CenterPost, safe_post_edit)
        if ep and ep.center_id == cid:
            gi = sorted(ep.images, key=lambda x: (x.sort_order, x.id))
            editing_post = {
                "id": ep.id,
                "title": ep.title,
                "summary": ep.summary or "",
                "body": ep.body or "",
                "post_type": ep.post_type,
                "is_pinned": ep.is_pinned,
                "is_published": ep.is_published,
                "cover_image_url": ep.cover_image_url or "",
                "gallery": [{"id": g.id, "url": g.image_url} for g in gi],
            }

    center_post_type_choices = [
        {"value": k, "label": v} for k, v in sorted(_s.CENTER_POST_TYPE_LABELS.items(), key=lambda x: x[1])
    ]

    return CenterPostsBundle(
        center_post_admin_rows=center_post_admin_rows,
        editing_post=editing_post,
        center_post_type_choices=center_post_type_choices,
        safe_post_edit=safe_post_edit,
        safe_center_posts_page=safe_center_posts_page,
        center_posts_total=center_posts_total,
        center_posts_total_pages=center_posts_total_pages,
        center_posts_page_size=center_posts_page_size,
    )

from urllib.parse import urlparse

from .web_shared import _fmt_dt, _url_with_params


def preview_text(text: str | None, max_len: int = 100) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def build_public_posts_blocks(
    *,
    pinned_post,
    recent_posts: list,
    center_id: int,
    type_labels: dict[str, str],
) -> tuple[dict | None, list[dict], list[dict[str, str]]]:
    pinned_public_post = None
    if pinned_post:
        sum_full = (pinned_post.summary or "").strip()
        pinned_public_post = {
            "id": pinned_post.id,
            "title": pinned_post.title,
            "post_type": pinned_post.post_type,
            "type_label": type_labels.get(pinned_post.post_type, pinned_post.post_type),
            "summary": sum_full,
            "summary_short": preview_text(sum_full, 100),
            "cover_image_url": pinned_post.cover_image_url,
            "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(pinned_post.id)),
        }

    public_posts_teasers: list[dict] = []
    news_ticker_items: list[dict[str, str]] = []
    if pinned_post:
        news_ticker_items.append(
            {
                "title": (pinned_post.title or "").strip(),
                "type_label": type_labels.get(pinned_post.post_type, pinned_post.post_type),
                "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(pinned_post.id)),
            }
        )

    for p in recent_posts:
        if pinned_post and p.id == pinned_post.id:
            continue
        if len(public_posts_teasers) < 3:
            sum_full = (p.summary or "").strip()
            public_posts_teasers.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "post_type": p.post_type,
                    "type_label": type_labels.get(p.post_type, p.post_type),
                    "summary": preview_text(sum_full, 120),
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
                        "type_label": type_labels.get(p.post_type, p.post_type),
                        "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                    }
                )
        if len(public_posts_teasers) >= 3 and len(news_ticker_items) >= 14:
            break
    return pinned_public_post, public_posts_teasers, news_ticker_items


def build_public_news_list_rows(*, posts: list, center_id: int, type_labels: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for p in posts:
        sum_full = (p.summary or "").strip()
        rows.append(
            {
                "title": p.title,
                "post_type": p.post_type,
                "type_label": type_labels.get(p.post_type, p.post_type),
                "summary": preview_text(sum_full, 180),
                "published_at_display": _fmt_dt(p.published_at) if p.published_at else "",
                "detail_url": _url_with_params("/post", center_id=str(center_id), post_id=str(p.id)),
                "cover_image_url": p.cover_image_url,
                "is_pinned": bool(p.is_pinned),
            }
        )
    return rows


def build_public_news_filter_options(
    *,
    post_types: set[str],
    type_labels: dict[str, str],
    sort_modes: set[str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    post_type_filter_options = [("", "كل الأنواع")] + [(k, type_labels[k]) for k in sorted(post_types)]
    default_sort_labels = {
        "newest": "الأحدث نشراً",
        "oldest": "الأقدم نشراً",
        "recent": "آخر إضافة",
    }
    sort_filter_options = [(k, default_sort_labels.get(k, k)) for k in ("newest", "oldest", "recent") if k in sort_modes]
    return post_type_filter_options, sort_filter_options


def index_preconnect_origins(
    request,
    center,
    pinned_public_post: dict | None,
    public_posts_teasers: list[dict],
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    try:
        cur = urlparse(str(request.url))
        current_host = (cur.hostname or "").lower()
    except Exception:
        current_host = ""

    def add_url(url: str | None) -> None:
        if not url or not isinstance(url, str):
            return
        u = url.strip()
        if not u.startswith(("http://", "https://")):
            return
        try:
            p = urlparse(u)
            if p.scheme not in ("http", "https") or not p.netloc:
                return
            host = (p.hostname or "").lower()
            if host == current_host:
                return
            origin = f"{p.scheme}://{p.netloc}"
            if origin not in seen:
                seen.add(origin)
                out.append(origin)
        except Exception:
            return

    add_url(getattr(center, "hero_image_url", None))
    add_url(getattr(center, "logo_url", None))
    if pinned_public_post:
        add_url(pinned_public_post.get("cover_image_url"))
    for t in public_posts_teasers or []:
        add_url(t.get("cover_image_url"))
    return out

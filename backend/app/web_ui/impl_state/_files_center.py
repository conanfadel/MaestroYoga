"""Resolve static URLs, clear missing branding files, and center post upload paths."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ... import models
from . import _paths
from ._constants import CENTER_POST_REMOTE_URL_MAX_LEN


def _resolved_path_under_static(public_path: str | None) -> Path | None:
    if not public_path or not isinstance(public_path, str):
        return None
    u = public_path.strip()
    if not u.startswith("/static/"):
        return None
    rel = u[len("/static/") :].strip("/")
    if not rel:
        return None
    parts = rel.split("/")
    if any(p == ".." or p == "" for p in parts):
        return None
    base = _paths.APP_STATIC_ROOT.resolve()
    candidate = (base / Path(*parts)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _clear_center_branding_urls_if_files_missing(db: Session, center: models.Center) -> None:
    changed = False
    lp = _resolved_path_under_static(center.logo_url)
    if lp is not None and not lp.is_file():
        center.logo_url = None
        changed = True
    hp = _resolved_path_under_static(center.hero_image_url)
    if hp is not None and not hp.is_file():
        center.hero_image_url = None
        center.hero_show_stock_photo = True
        changed = True
    if changed:
        db.add(center)
        db.commit()


def _unlink_center_uploads(glob_pattern: str) -> None:
    if not _paths.CENTER_LOGO_UPLOAD_DIR.is_dir():
        return
    for path in _paths.CENTER_LOGO_UPLOAD_DIR.glob(glob_pattern):
        path.unlink(missing_ok=True)


def _sanitize_center_post_remote_image_url(raw: str | None) -> str | None:
    """يقبل فقط http/https لعرضها في المتصفح (بدون تنزيل من الخادم)."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > CENTER_POST_REMOTE_URL_MAX_LEN:
        return None
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    return s


def _parse_center_post_gallery_remote_urls(blob: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in (blob or "").splitlines():
        for part in line.split(","):
            u = _sanitize_center_post_remote_image_url(part)
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _delete_center_post_disk_files(center_id: int, post_id: int) -> None:
    if not _paths.CENTER_POST_UPLOAD_DIR.is_dir():
        return
    prefix = f"center_{center_id}_post_{post_id}_"
    for path in _paths.CENTER_POST_UPLOAD_DIR.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            path.unlink(missing_ok=True)


def _unlink_static_url_file(public_url: str | None) -> None:
    p = _resolved_path_under_static(public_url)
    if p and p.is_file():
        p.unlink(missing_ok=True)

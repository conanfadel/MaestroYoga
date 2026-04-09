"""Public content version JSON (for cache busting / polling)."""

from __future__ import annotations

from fastapi import APIRouter

from . import impl_state as _s


def register_public_browse_utils_routes(router: APIRouter) -> None:
    @router.get("/public/content-version")
    def public_content_version(center_id: int = 1, db: _s.Session = _s.Depends(_s.get_db)):
        return {"center_id": center_id, "version": _s.compute_public_center_content_version(db, center_id)}

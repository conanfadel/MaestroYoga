"""Demo seed endpoint (guarded by key or local client)."""

from __future__ import annotations

try:
    from ..bootstrap import ensure_demo_data
except ImportError:
    from backend.app.bootstrap import ensure_demo_data

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from . import deps as _d
from .config import SEED_DEMO_KEY
from .helpers import is_local_client


def register_routes(router: APIRouter) -> None:
    @router.post("/seed-demo")
    def seed_demo(
        request: Request,
        x_seed_demo_key: str = Header(default="", alias="X-Seed-Demo-Key"),
        db: Session = Depends(_d.get_db),
    ):
        if SEED_DEMO_KEY:
            if x_seed_demo_key.strip() != SEED_DEMO_KEY:
                raise HTTPException(status_code=403, detail="Forbidden")
        elif not is_local_client(request):
            # Safe default: allow only local callers unless explicit key is configured.
            raise HTTPException(status_code=403, detail="Forbidden")
        center = ensure_demo_data(db)
        return {
            "message": "Demo data ready",
            "center_id": center.id,
        }

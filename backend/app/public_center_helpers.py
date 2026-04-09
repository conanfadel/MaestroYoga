from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models
from .bootstrap import DEMO_CENTER_NAME, ensure_demo_data


def resolve_public_center_or_404(db: Session, center_id: int | None) -> models.Center:
    """Resolve the center for public pages, preserving existing fallback behavior."""
    effective_center_id = int(center_id) if isinstance(center_id, int) else None
    if effective_center_id is None:
        first_non_demo = (
            db.query(models.Center.id)
            .filter(models.Center.name != DEMO_CENTER_NAME)
            .order_by(models.Center.id.asc())
            .first()
        )
        if first_non_demo and first_non_demo[0]:
            effective_center_id = int(first_non_demo[0])
        else:
            first_any = db.query(models.Center.id).order_by(models.Center.id.asc()).first()
            effective_center_id = int(first_any[0]) if first_any and first_any[0] else 1

    center = db.get(models.Center, effective_center_id)
    if not center:
        ensure_demo_data(db)
        center = db.get(models.Center, effective_center_id)
        if not center:
            center = db.query(models.Center).order_by(models.Center.id.asc()).first()
    if not center:
        raise HTTPException(status_code=404, detail="Center not found")
    return center

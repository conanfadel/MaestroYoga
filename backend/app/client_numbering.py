"""Client subscription-number helpers (4-digit display, per center sequence)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def next_client_subscription_number(db: Session, *, center_id: int) -> int:
    """Return next per-center running number (1-based)."""
    current_max = (
        db.query(func.max(models.Client.subscription_number))
        .filter(models.Client.center_id == center_id)
        .scalar()
    )
    return int(current_max or 0) + 1


def ensure_client_subscription_number(db: Session, *, client: models.Client) -> int:
    """Assign number if missing and return it."""
    if client.subscription_number and int(client.subscription_number) > 0:
        return int(client.subscription_number)
    number = next_client_subscription_number(db, center_id=int(client.center_id))
    client.subscription_number = number
    return number


def format_client_subscription_number(number: int | None) -> str:
    """Return 4-digit string for UI display (0001...)."""
    if number is None:
        return "—"
    try:
        value = int(number)
    except (TypeError, ValueError):
        return "—"
    if value <= 0:
        return "—"
    return f"{value:04d}"

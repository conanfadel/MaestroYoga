"""Helpers shared across REST payment, checkout, and webhook-related code."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy.orm import Session

from . import deps as _d


def payments_query(db: Session, center_id: int, client_id: int | None = None, status: str | None = None):
    query = db.query(_d.models.Payment).filter(_d.models.Payment.center_id == center_id)
    if client_id is not None:
        query = query.filter(_d.models.Payment.client_id == client_id)
    if status:
        query = query.filter(_d.models.Payment.status == status)
    return query


def allowed_checkout_origins() -> list[str]:
    from .config import PUBLIC_BASE_URL, STRIPE_CHECKOUT_ALLOWED_ORIGINS

    if STRIPE_CHECKOUT_ALLOWED_ORIGINS:
        return STRIPE_CHECKOUT_ALLOWED_ORIGINS
    if PUBLIC_BASE_URL:
        return [PUBLIC_BASE_URL]
    return ["http://127.0.0.1:8000", "http://localhost:8000"]


def is_checkout_redirect_allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return origin in allowed_checkout_origins()


def is_local_client(request: Request) -> bool:
    if not request.client:
        return False
    host = request.client.host or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def moyasar_extract_invoice_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    pid = payload.get("id")
    if isinstance(pid, str) and len(pid) > 10:
        return pid
    data = payload.get("data")
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    inv = payload.get("invoice")
    if isinstance(inv, dict) and inv.get("id"):
        return str(inv["id"])
    return str(pid) if pid else None

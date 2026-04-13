"""FastAPI lifespan hook."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def _stale_payment_sweeper_loop() -> None:
    """Periodically cancel stale ``pending_payment`` bookings and failed orphan checkouts."""
    try:
        from .checkout_finalize import expire_stale_pending_payments
        from .database import SessionLocal
    except ImportError:
        from backend.app.checkout_finalize import expire_stale_pending_payments
        from backend.app.database import SessionLocal

    interval = int(os.getenv("STALE_PAYMENT_SWEEP_INTERVAL_SEC", "900") or "900")
    minutes = int(os.getenv("PENDING_PAYMENT_EXPIRE_MINUTES", "180") or "180")
    await asyncio.sleep(60)
    while True:
        db = SessionLocal()
        try:
            n = expire_stale_pending_payments(db, older_than_minutes=minutes)
            if n:
                logger.info("stale_payment_sweeper: expired %s pending payment row(s)", n)
        except Exception:
            logger.exception("stale_payment_sweeper failed")
        finally:
            db.close()
        await asyncio.sleep(max(60, interval))


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    lvl_name = os.getenv("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    logging.getLogger("maestro.request").setLevel(lvl)

    sweeper_task: asyncio.Task | None = None
    if os.getenv("DISABLE_STALE_PAYMENT_SWEEPER", "").strip().lower() not in ("1", "true", "yes"):
        sweeper_task = asyncio.create_task(_stale_payment_sweeper_loop())

    try:
        yield
    finally:
        if sweeper_task:
            sweeper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sweeper_task

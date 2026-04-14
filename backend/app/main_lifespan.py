"""FastAPI lifespan hook."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .logging_setup import configure_logging, init_sentry

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


async def _pending_payment_reconcile_loop() -> None:
    try:
        from .checkout_finalize import reconcile_stale_pending_payments
        from .database import SessionLocal
    except ImportError:
        from backend.app.checkout_finalize import reconcile_stale_pending_payments
        from backend.app.database import SessionLocal

    interval = int(os.getenv("PAYMENT_RECONCILE_INTERVAL_SEC", "300") or "300")
    older = int(os.getenv("PAYMENT_RECONCILE_OLDER_THAN_MINUTES", "5") or "5")
    await asyncio.sleep(75)
    while True:
        db = SessionLocal()
        try:
            stats = reconcile_stale_pending_payments(db, older_than_minutes=older, max_rows=200)
            if int(stats.get("paid", 0) or 0) or int(stats.get("failed", 0) or 0):
                logger.info("payment_reconcile: %s", stats)
        except Exception:
            logger.exception("payment_reconcile loop failed")
        finally:
            db.close()
        await asyncio.sleep(max(60, interval))


async def _webhook_delay_monitor_loop() -> None:
    try:
        from .checkout_finalize import monitor_delayed_webhook_payments, send_operational_alert
        from .database import SessionLocal
    except ImportError:
        from backend.app.checkout_finalize import monitor_delayed_webhook_payments, send_operational_alert
        from backend.app.database import SessionLocal

    interval = int(os.getenv("PAYMENT_WEBHOOK_DELAY_MONITOR_INTERVAL_SEC", "600") or "600")
    overdue = int(os.getenv("PAYMENT_WEBHOOK_DELAY_MINUTES", "10") or "10")
    alert_threshold = int(os.getenv("OPS_PENDING_OVERDUE_ALERT_THRESHOLD", "5") or "5")
    alert_cooldown_sec = int(os.getenv("OPS_ALERT_COOLDOWN_SEC", "900") or "900")
    last_alert_at = 0.0
    await asyncio.sleep(90)
    while True:
        db = SessionLocal()
        try:
            n = monitor_delayed_webhook_payments(db, overdue_minutes=overdue, max_rows=100)
            if n:
                logger.warning("webhook_delay_monitor: recorded %s delayed pending payment alert(s)", n)
            now_mono = time.monotonic()
            if n >= max(1, alert_threshold) and (now_mono - last_alert_at) >= max(60, alert_cooldown_sec):
                ok = send_operational_alert(
                    title="Pending payments overdue",
                    body=(
                        f"Detected {n} pending payments older than {overdue} minutes. "
                        "Check webhook health and payment provider delivery."
                    ),
                    count=n,
                )
                if ok:
                    last_alert_at = now_mono
        except Exception:
            logger.exception("webhook_delay_monitor loop failed")
        finally:
            db.close()
        await asyncio.sleep(max(120, interval))


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    configure_logging()
    init_sentry()
    lvl_name = os.getenv("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    logging.getLogger("maestro.request").setLevel(lvl)

    sweeper_task: asyncio.Task | None = None
    reconcile_task: asyncio.Task | None = None
    delay_monitor_task: asyncio.Task | None = None
    if os.getenv("DISABLE_STALE_PAYMENT_SWEEPER", "").strip().lower() not in ("1", "true", "yes"):
        sweeper_task = asyncio.create_task(_stale_payment_sweeper_loop())
    if os.getenv("DISABLE_PAYMENT_RECONCILE", "").strip().lower() not in ("1", "true", "yes"):
        reconcile_task = asyncio.create_task(_pending_payment_reconcile_loop())
    if os.getenv("DISABLE_WEBHOOK_DELAY_MONITOR", "").strip().lower() not in ("1", "true", "yes"):
        delay_monitor_task = asyncio.create_task(_webhook_delay_monitor_loop())

    try:
        yield
    finally:
        if sweeper_task:
            sweeper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sweeper_task
        if reconcile_task:
            reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reconcile_task
        if delay_monitor_task:
            delay_monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await delay_monitor_task

"""Root logging configuration: optional JSON lines for aggregators (Loki, CloudWatch, etc.)."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class _JsonLineFormatter(logging.Formatter):
    """One JSON object per line; suitable for log shipping."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Apply LOG_LEVEL; if LOG_FORMAT=json, attach a JSON line handler to the root logger."""
    lvl_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, lvl_name, logging.INFO)
    log_format = (os.getenv("LOG_FORMAT") or "text").strip().lower()

    root = logging.getLogger()
    root.setLevel(level)

    if getattr(root, "_maestro_json_logging", False):
        return

    if log_format != "json":
        setattr(root, "_maestro_json_logging", True)
        return

    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonLineFormatter())
    root.addHandler(handler)
    setattr(root, "_maestro_json_logging", True)


def init_sentry() -> None:
    """Optional error tracking when SENTRY_DSN is set and sentry-sdk is installed."""
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; pip install sentry-sdk"
        )
        return

    traces = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or "0")
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=traces,
        environment=os.getenv("APP_ENV", "development"),
    )

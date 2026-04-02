import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .models import SecurityAuditEvent
from .request_ip import get_client_ip

_LOGGER_NAME = "maestro.security.audit"
_logger = logging.getLogger(_LOGGER_NAME)
_configured = False
_executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("SECURITY_AUDIT_ASYNC_WORKERS", "1"))))


def _is_async_enabled() -> bool:
    return os.getenv("SECURITY_AUDIT_ASYNC", "0").strip().lower() in {"1", "true", "yes", "on"}


def _configure_logger() -> None:
    global _configured
    if _configured:
        return

    log_file = os.getenv("SECURITY_AUDIT_LOG_FILE", "logs/security_audit.log")
    max_bytes = int(os.getenv("SECURITY_AUDIT_LOG_MAX_BYTES", "2097152"))  # 2 MB
    backups = int(os.getenv("SECURITY_AUDIT_LOG_BACKUPS", "5"))

    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(message)s")
    handler.setFormatter(formatter)

    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    _logger.addHandler(handler)
    _configured = True


def log_security_event(
    event_type: str,
    request: Request,
    status: str,
    email: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    _configure_logger()
    payload: dict[str, Any] = {
        "event_type": event_type,
        "status": status,
        "email": (email or "").lower().strip(),
        "ip": get_client_ip(request),
        "user_agent": request.headers.get("user-agent", ""),
        "path": str(request.url.path),
        "details": details or {},
    }
    _logger.info(json.dumps(payload, ensure_ascii=True))
    if _is_async_enabled():
        _executor.submit(_save_event_db, payload)
    else:
        _save_event_db(payload)


def _save_event_db(payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        row = SecurityAuditEvent(
            event_type=str(payload.get("event_type", "")),
            status=str(payload.get("status", "")),
            email=str(payload.get("email", "")) or None,
            ip=str(payload.get("ip", "")) or None,
            user_agent=str(payload.get("user_agent", "")) or None,
            path=str(payload.get("path", "")) or None,
            details_json=json.dumps(payload.get("details", {}), ensure_ascii=True),
        )
        db.add(row)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
    finally:
        db.close()

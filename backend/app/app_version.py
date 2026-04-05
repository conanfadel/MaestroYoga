"""مصدر واحد لرقم إصدار التطبيق (واجهة + API + كاش CSS)."""

from __future__ import annotations

import os
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _APP_ROOT / "version.txt"


def _read_version_file() -> str | None:
    try:
        if _VERSION_FILE.is_file():
            raw = _VERSION_FILE.read_text(encoding="utf-8").strip()
            return raw[:80] if raw else None
    except OSError:
        pass
    return None


def get_app_version() -> str:
    env = os.getenv("APP_VERSION", "").strip()
    if env:
        return env[:80]
    from_file = _read_version_file()
    if from_file:
        return from_file
    return "1.0.0"


APP_VERSION_STRING = get_app_version()

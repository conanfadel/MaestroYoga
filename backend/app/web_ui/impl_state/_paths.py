"""Filesystem paths for templates, static assets, and center uploads."""

from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_WEB_UI_DIR = _PKG_DIR.parent
_APP_DIR = _WEB_UI_DIR.parent
BACKEND_ROOT = _APP_DIR.parent

TEMPLATES_DIR = BACKEND_ROOT / "templates"
APP_STATIC_ROOT = BACKEND_ROOT / "static"
CENTER_LOGO_UPLOAD_DIR = APP_STATIC_ROOT / "uploads" / "centers"
CENTER_POST_UPLOAD_DIR = CENTER_LOGO_UPLOAD_DIR / "posts"

"""Assemble FastAPI app: middleware, static files, REST UI, webhooks."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in non-venv runtime
    def load_dotenv() -> bool:  # type: ignore[override]
        return False

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

try:
    from .database import init_db
    from .middleware import (
        ApiClientHeadersMiddleware,
        MaintenanceMiddleware,
        RateLimitMiddleware,
        RequestIDMiddleware,
        attach_cors,
    )
    from .web_ui import router as web_ui_router
except ImportError:
    from backend.app.database import init_db
    from backend.app.middleware import (
        ApiClientHeadersMiddleware,
        MaintenanceMiddleware,
        RateLimitMiddleware,
        RequestIDMiddleware,
        attach_cors,
    )
    from backend.app.web_ui import router as web_ui_router

from .main_lifespan import app_lifespan
from .main_meta import build_api_v1_meta_router
from .main_rest_api import api_router
from .main_webhooks import webhooks_router


def create_app() -> FastAPI:
    load_dotenv()
    app = FastAPI(title="Maestro Yoga API", version="1.0.0", lifespan=app_lifespan)

    init_db()
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(ApiClientHeadersMiddleware)
    app.add_middleware(MaintenanceMiddleware)
    _cors_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
    attach_cors(app, _cors_origins)
    app.add_middleware(RateLimitMiddleware)
    app.include_router(web_ui_router)
    _static_dir = Path(__file__).resolve().parent.parent / "static"
    if _static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    app.include_router(webhooks_router)
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(build_api_v1_meta_router(server_version=app.version))

    return app

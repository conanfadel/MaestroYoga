"""ASGI entry: `uvicorn backend.app.main:app` or `python -m backend.app.main`."""

from __future__ import annotations

from pathlib import Path

from .main_bootstrap import run_early_setup

run_early_setup(Path(__file__).resolve(), is_main=(__name__ == "__main__"))

from .main_app import create_app

app = create_app()

if __name__ == "__main__":
    import os

    import uvicorn

    reload_enabled = os.getenv("UVICORN_RELOAD", "1").strip().lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=reload_enabled)

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _venv_python() -> Path:
    if os.name == "nt":
        return PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT / ".venv" / "bin" / "python"


def _ensure_venv_runtime_for_direct_run() -> None:
    if __name__ != "__main__":
        return
    target = _venv_python()
    if not target.exists():
        return
    current = Path(sys.executable).resolve()
    if current != target.resolve():
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run(
            [str(target), str(Path(__file__).resolve())],
            cwd=str(PROJECT_ROOT),
            env=env,
            check=False,
        )
        if result.returncode == 0:
            raise SystemExit(0)
        print(
            (
                f"[main.py] Warning: failed to switch to venv interpreter '{target}' "
                f"(exit code {result.returncode}). Continuing with '{current}'. "
                "Rebuild .venv if needed."
            ),
            file=sys.stderr,
        )


_ensure_venv_runtime_for_direct_run()

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in non-venv runtime
    def load_dotenv() -> bool:  # type: ignore[override]
        return False
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

try:
    from .checkout_finalize import finalize_checkout_failed, finalize_checkout_paid
    from .database import get_db, init_db
    from .middleware import (
        ApiClientHeadersMiddleware,
        MaintenanceMiddleware,
        RateLimitMiddleware,
        RequestIDMiddleware,
        attach_cors,
    )
    from .payments import MoyasarPaymentProvider, StripePaymentProvider
    from .web_ui import router as web_ui_router
except ImportError:
    from backend.app.checkout_finalize import finalize_checkout_failed, finalize_checkout_paid
    from backend.app.database import get_db, init_db
    from backend.app.middleware import (
        ApiClientHeadersMiddleware,
        MaintenanceMiddleware,
        RateLimitMiddleware,
        RequestIDMiddleware,
        attach_cors,
    )
    from backend.app.payments import MoyasarPaymentProvider, StripePaymentProvider
    from backend.app.web_ui import router as web_ui_router

from .main_rest_api import api_router, _moyasar_extract_invoice_id

load_dotenv()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    lvl_name = os.getenv("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    logging.getLogger("maestro.request").setLevel(lvl)
    yield


app = FastAPI(title="Maestro Yoga API", version="1.0.0", lifespan=_app_lifespan)

init_db()
app.add_middleware(RequestIDMiddleware)
app.add_middleware(ApiClientHeadersMiddleware)
app.add_middleware(MaintenanceMiddleware)
_cors_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
attach_cors(app, _cors_origins)
app.add_middleware(RateLimitMiddleware)
app.include_router(web_ui_router)
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.post("/payments/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()
    try:
        event = StripePaymentProvider.construct_event(payload, stripe_signature)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}")

    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        session_id = event_data.get("id") or ""
        metadata = dict(event_data.get("metadata", {}) or {})
        finalize_checkout_paid(db, metadata, str(session_id))
    elif event_type == "checkout.session.expired":
        session_id = event_data.get("id") or ""
        metadata = dict(event_data.get("metadata", {}) or {})
        finalize_checkout_failed(db, metadata, str(session_id))

    return {"received": True}


@app.post("/payments/webhook/moyasar")
async def moyasar_invoice_webhook(request: Request, db: Session = Depends(get_db)):
    """إشعار ميسر عند دفع الفاتورة (callback_url). يُنصح بالتحقق عبر API."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    invoice_id = _moyasar_extract_invoice_id(payload)
    if not invoice_id:
        return {"received": True}
    try:
        fresh = MoyasarPaymentProvider.fetch_invoice(str(invoice_id))
    except Exception as exc:
        logging.getLogger(__name__).warning("moyasar invoice fetch failed: %s", exc)
        return {"received": True}
    if fresh.get("status") != "paid":
        return {"received": True}
    meta = dict(fresh.get("metadata") or {})
    finalize_checkout_paid(db, meta, str(invoice_id))
    return {"received": True}


api_v1_meta_router = APIRouter(prefix="/api/v1", tags=["api-v1"])


@api_v1_meta_router.get("/meta")
def api_v1_meta():
    """نقطة دخول موحّدة لتطبيق أندرويد: إصدار الـ API وروابط التوثيق."""
    return {
        "api_version": "1",
        "app": "Maestro Yoga",
        "server_version": app.version,
        "openapi_json": "/openapi.json",
        "docs": "/docs",
        "client_hint": "أرسل الرأس X-App-Version (مثل 1.0.0) ليُعاد في X-App-Version-Accepted.",
    }


app.include_router(api_router)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_v1_meta_router)
if __name__ == "__main__":
    import uvicorn

    reload_enabled = os.getenv("UVICORN_RELOAD", "1").strip().lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=reload_enabled)

import csv
import io
from datetime import datetime, timezone
from io import BytesIO
import logging
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

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
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from . import models, schemas
    from .booking_utils import count_active_bookings
    from .bootstrap import DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD, ensure_demo_data
    from .checkout_finalize import finalize_checkout_failed, finalize_checkout_paid
    from .database import get_db, init_db
    from .payments import (
        MoyasarPaymentProvider,
        StripePaymentProvider,
        get_payment_provider,
        payment_provider_supports_hosted_checkout,
    )
    from .security import create_access_token, get_current_user, hash_password, require_roles, verify_password
    from .web_ui import router as web_ui_router
    from .tenant_utils import require_user_center_id
except ImportError:
    from backend.app import models, schemas
    from backend.app.booking_utils import count_active_bookings
    from backend.app.bootstrap import DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD, ensure_demo_data
    from backend.app.checkout_finalize import finalize_checkout_failed, finalize_checkout_paid
    from backend.app.database import get_db, init_db
    from backend.app.payments import (
        MoyasarPaymentProvider,
        StripePaymentProvider,
        get_payment_provider,
        payment_provider_supports_hosted_checkout,
    )
    from backend.app.security import create_access_token, get_current_user, hash_password, require_roles, verify_password
    from backend.app.web_ui import router as web_ui_router
    from backend.app.tenant_utils import require_user_center_id

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Maestro Yoga API", version="1.0.0")
init_db()
app.include_router(web_ui_router)
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
SEED_DEMO_KEY = os.getenv("SEED_DEMO_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
STRIPE_CHECKOUT_ALLOWED_ORIGINS = [x.strip().rstrip("/") for x in os.getenv("STRIPE_CHECKOUT_ALLOWED_ORIGINS", "").split(",") if x.strip()]


@app.get("/")
def root():
    return {"app": "Maestro Yoga", "status": "running"}


@app.get("/health")
def health():
    """مسار خفيف لفحص الصحة على Render وغيره (بدون اتصال بقاعدة البيانات)."""
    return {"status": "ok"}


def _payments_query(db: Session, center_id: int, client_id: int | None = None, status: str | None = None):
    query = db.query(models.Payment).filter(models.Payment.center_id == center_id)
    if client_id is not None:
        query = query.filter(models.Payment.client_id == client_id)
    if status:
        query = query.filter(models.Payment.status == status)
    return query


def _allowed_checkout_origins() -> list[str]:
    if STRIPE_CHECKOUT_ALLOWED_ORIGINS:
        return STRIPE_CHECKOUT_ALLOWED_ORIGINS
    if PUBLIC_BASE_URL:
        return [PUBLIC_BASE_URL]
    return ["http://127.0.0.1:8000", "http://localhost:8000"]


def _is_checkout_redirect_allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return origin in _allowed_checkout_origins()


def _is_local_client(request: Request) -> bool:
    if not request.client:
        return False
    host = request.client.host or ""
    return host in {"127.0.0.1", "::1", "localhost"}


@app.get("/dashboard/summary", response_model=schemas.DashboardSummaryOut)
def dashboard_summary(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    today = datetime.now(timezone.utc).date()

    clients_count = db.query(models.Client).filter(models.Client.center_id == center_id).count()
    sessions_count = db.query(models.YogaSession).filter(models.YogaSession.center_id == center_id).count()
    bookings_count = db.query(models.Booking).filter(models.Booking.center_id == center_id).count()
    active_plans_count = (
        db.query(models.SubscriptionPlan)
        .filter(models.SubscriptionPlan.center_id == center_id, models.SubscriptionPlan.is_active.is_(True))
        .count()
    )
    revenue_total = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .filter(models.Payment.center_id == center_id, models.Payment.status == "paid")
        .scalar()
    )
    revenue_today = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0.0))
        .filter(
            models.Payment.center_id == center_id,
            models.Payment.status == "paid",
            func.date(models.Payment.paid_at) == today,
        )
        .scalar()
    )
    pending_payments_count = (
        db.query(models.Payment)
        .filter(models.Payment.center_id == center_id, models.Payment.status == "pending")
        .count()
    )

    return {
        "center_id": center_id,
        "clients_count": clients_count,
        "sessions_count": sessions_count,
        "bookings_count": bookings_count,
        "active_plans_count": active_plans_count,
        "revenue_total": float(revenue_total or 0.0),
        "revenue_today": float(revenue_today or 0.0),
        "pending_payments_count": pending_payments_count,
    }


@app.post("/auth/register", response_model=schemas.TokenOut)
def register_owner(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    exists = db.query(models.User).filter(models.User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    center = models.Center(name=payload.center_name, city=payload.city)
    db.add(center)
    db.flush()

    owner = models.User(
        center_id=center.id,
        full_name=payload.full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role="center_owner",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    token = create_access_token(owner.id)
    return {"access_token": token, "user": owner}


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")
    token = create_access_token(user.id)
    return {"access_token": token, "user": user}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@app.post("/auth/users", response_model=schemas.UserOut)
def create_user_by_owner(
    payload: schemas.UserCreateByOwner,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner")),
):
    exists = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")
    new_user = models.User(
        center_id=user.center_id,
        full_name=payload.full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/centers", response_model=schemas.CenterOut)
def create_center(
    payload: schemas.CenterCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("superadmin")),
):
    center = models.Center(**payload.model_dump())
    db.add(center)
    db.commit()
    db.refresh(center)
    return center


@app.get("/centers", response_model=list[schemas.CenterOut])
def list_centers(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role == "superadmin":
        return db.query(models.Center).all()
    center_id = require_user_center_id(user)
    center = db.get(models.Center, center_id)
    return [center] if center else []


@app.post("/clients", response_model=schemas.ClientOut)
def create_client(
    payload: schemas.ClientCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    client = models.Client(center_id=require_user_center_id(user), **payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@app.get("/clients", response_model=list[schemas.ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return db.query(models.Client).filter(models.Client.center_id == require_user_center_id(user)).all()


@app.post("/plans", response_model=schemas.SubscriptionPlanOut)
def create_plan(
    payload: schemas.SubscriptionPlanCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    plan = models.SubscriptionPlan(center_id=require_user_center_id(user), **payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@app.get("/plans", response_model=list[schemas.SubscriptionPlanOut])
def list_plans(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return db.query(models.SubscriptionPlan).filter(models.SubscriptionPlan.center_id == require_user_center_id(user)).all()


@app.post("/rooms", response_model=schemas.RoomOut)
def create_room(
    payload: schemas.RoomCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff")),
):
    room = models.Room(center_id=require_user_center_id(user), **payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@app.post("/sessions", response_model=schemas.YogaSessionOut)
def create_session(
    payload: schemas.YogaSessionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("center_owner", "center_staff", "trainer")),
):
    center_id = require_user_center_id(user)
    room = db.get(models.Room, payload.room_id)
    if not room or room.center_id != center_id:
        raise HTTPException(status_code=404, detail="Room not found for center")
    yoga_session = models.YogaSession(center_id=center_id, **payload.model_dump())
    db.add(yoga_session)
    db.commit()
    db.refresh(yoga_session)
    return yoga_session


@app.get("/sessions", response_model=list[schemas.YogaSessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return db.query(models.YogaSession).filter(models.YogaSession.center_id == require_user_center_id(user)).all()


@app.post("/bookings", response_model=schemas.BookingOut)
def create_booking(
    payload: schemas.BookingCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    session = db.get(models.YogaSession, payload.session_id)
    client = db.get(models.Client, payload.client_id)
    if not session or not client:
        raise HTTPException(status_code=404, detail="Session or client not found")
    if session.center_id != center_id or client.center_id != center_id:
        raise HTTPException(status_code=400, detail="Center mismatch")

    room = db.get(models.Room, session.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found for session")
    if count_active_bookings(db, session.id) >= room.capacity:
        raise HTTPException(status_code=400, detail="Room is full")

    booking = models.Booking(center_id=center_id, **payload.model_dump(), status="confirmed")
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@app.post("/payments", response_model=schemas.PaymentOut)
def create_payment(
    payload: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    client = db.get(models.Client, payload.client_id)
    if not client or client.center_id != center_id:
        raise HTTPException(status_code=404, detail="Client not found for center")

    provider = get_payment_provider()
    if payment_provider_supports_hosted_checkout(provider):
        raise HTTPException(
            status_code=400,
            detail="Use /payments/checkout-session for Stripe or Moyasar payments",
        )
    provider_result = provider.charge(
        amount=payload.amount,
        currency=payload.currency,
        metadata={"center_id": center_id, "client_id": payload.client_id},
    )

    payment = models.Payment(
        center_id=center_id,
        booking_id=None,
        **payload.model_dump(),
        provider_ref=provider_result.provider_ref,
        status=provider_result.status,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@app.post("/payments/checkout-session", response_model=schemas.PaymentCheckoutOut)
def create_checkout_session(
    payload: schemas.PaymentCheckoutCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    client = db.get(models.Client, payload.client_id)
    if not client or client.center_id != center_id:
        raise HTTPException(status_code=404, detail="Client not found for center")

    provider = get_payment_provider()
    if not payment_provider_supports_hosted_checkout(provider):
        raise HTTPException(status_code=400, detail="Checkout session requires Stripe or Moyasar provider")
    if not _is_checkout_redirect_allowed(payload.success_url) or not _is_checkout_redirect_allowed(payload.cancel_url):
        raise HTTPException(
            status_code=400,
            detail="success_url/cancel_url must match allowed checkout origins",
        )

    pm = "moyasar_checkout" if isinstance(provider, MoyasarPaymentProvider) else "stripe_checkout"
    payment = models.Payment(
        center_id=center_id,
        client_id=payload.client_id,
        booking_id=None,
        amount=payload.amount,
        currency=payload.currency.upper(),
        payment_method=pm,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        meta = {
            "payment_id": str(payment.id),
            "center_id": str(center_id),
            "client_id": str(payload.client_id),
        }
        if payment.booking_id:
            meta["booking_id"] = str(payment.booking_id)
        provider_result = provider.create_checkout_session(
            amount=payload.amount,
            currency=payload.currency,
            metadata=meta,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except Exception as exc:
        logger.exception("Failed to create Stripe checkout session: %s", exc)
        raise HTTPException(status_code=500, detail="Checkout session creation failed")

    payment.provider_ref = provider_result.provider_ref
    db.commit()
    db.refresh(payment)
    return {
        "payment_id": payment.id,
        "checkout_url": provider_result.checkout_url or "",
        "provider_ref": provider_result.provider_ref,
        "status": payment.status,
    }


@app.get("/payments/{payment_id}", response_model=schemas.PaymentOut)
def get_payment_status(
    payment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    payment = db.get(models.Payment, payment_id)
    if not payment or payment.center_id != center_id:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@app.get("/payments", response_model=list[schemas.PaymentOut])
def list_payments(
    client_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    query = _payments_query(db, center_id=center_id, client_id=client_id, status=status)
    return query.order_by(models.Payment.paid_at.desc()).all()


@app.get("/payments/export/csv")
def export_payments_csv(
    client_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    query = _payments_query(db, center_id=center_id, client_id=client_id, status=status)

    payments = query.order_by(models.Payment.paid_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "payment_id",
            "center_id",
            "client_id",
            "amount",
            "currency",
            "payment_method",
            "provider_ref",
            "status",
            "paid_at",
        ]
    )
    for payment in payments:
        writer.writerow(
            [
                payment.id,
                payment.center_id,
                payment.client_id,
                payment.amount,
                payment.currency,
                payment.payment_method,
                payment.provider_ref or "",
                payment.status,
                payment.paid_at.isoformat() if payment.paid_at else "",
            ]
        )

    filename = f"maestro_payments_center_{center_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    content = output.getvalue()
    output.close()
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers=headers)


@app.get("/payments/export/xlsx")
def export_payments_xlsx(
    client_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    center_id = require_user_center_id(user)
    query = _payments_query(db, center_id=center_id, client_id=client_id, status=status)
    payments = query.order_by(models.Payment.paid_at.desc()).all()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Payments"
    headers_row = [
        "payment_id",
        "center_id",
        "client_id",
        "amount",
        "currency",
        "payment_method",
        "provider_ref",
        "status",
        "paid_at",
    ]
    sheet.append(headers_row)
    for payment in payments:
        sheet.append(
            [
                payment.id,
                payment.center_id,
                payment.client_id,
                payment.amount,
                payment.currency,
                payment.payment_method,
                payment.provider_ref or "",
                payment.status,
                payment.paid_at.isoformat() if payment.paid_at else "",
            ]
        )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    filename = f"maestro_payments_center_{center_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


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


def _moyasar_extract_invoice_id(payload: object) -> str | None:
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


@app.post("/seed-demo")
def seed_demo(
    request: Request,
    x_seed_demo_key: str = Header(default="", alias="X-Seed-Demo-Key"),
    db: Session = Depends(get_db),
):
    if SEED_DEMO_KEY:
        if x_seed_demo_key.strip() != SEED_DEMO_KEY:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif not _is_local_client(request):
        # Safe default: allow only local callers unless explicit key is configured.
        raise HTTPException(status_code=403, detail="Forbidden")
    center = ensure_demo_data(db)
    return {
        "message": "Demo data ready",
        "center_id": center.id,
    }


if __name__ == "__main__":
    import uvicorn

    reload_enabled = os.getenv("UVICORN_RELOAD", "1").strip().lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=reload_enabled)

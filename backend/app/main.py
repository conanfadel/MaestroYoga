import csv
import io
from datetime import datetime, timezone
from io import BytesIO
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
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from . import models, schemas
    from .booking_utils import count_active_bookings
    from .bootstrap import DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD, ensure_demo_data
    from .database import get_db, init_db
    from .payments import StripePaymentProvider, get_payment_provider
    from .security import create_access_token, get_current_user, hash_password, require_roles, verify_password
    from .web_ui import router as web_ui_router
    from .tenant_utils import require_user_center_id
except ImportError:
    from backend.app import models, schemas
    from backend.app.booking_utils import count_active_bookings
    from backend.app.bootstrap import DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD, ensure_demo_data
    from backend.app.database import get_db, init_db
    from backend.app.payments import StripePaymentProvider, get_payment_provider
    from backend.app.security import create_access_token, get_current_user, hash_password, require_roles, verify_password
    from backend.app.web_ui import router as web_ui_router
    from backend.app.tenant_utils import require_user_center_id

load_dotenv()

app = FastAPI(title="Maestro Yoga API", version="1.0.0")
init_db()
app.include_router(web_ui_router)
SEED_DEMO_KEY = os.getenv("SEED_DEMO_KEY", "").strip()


@app.get("/")
def root():
    return {"app": "Maestro Yoga", "status": "running"}


def _payments_query(db: Session, center_id: int, client_id: int | None = None, status: str | None = None):
    query = db.query(models.Payment).filter(models.Payment.center_id == center_id)
    if client_id is not None:
        query = query.filter(models.Payment.client_id == client_id)
    if status:
        query = query.filter(models.Payment.status == status)
    return query


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
    if isinstance(provider, StripePaymentProvider):
        raise HTTPException(
            status_code=400,
            detail="Use /payments/checkout-session for Stripe payments",
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
    if not isinstance(provider, StripePaymentProvider):
        raise HTTPException(status_code=400, detail="Checkout session requires Stripe provider")

    payment = models.Payment(
        center_id=center_id,
        client_id=payload.client_id,
        booking_id=None,
        amount=payload.amount,
        currency=payload.currency.upper(),
        payment_method="stripe_checkout",
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
        raise HTTPException(status_code=500, detail=str(exc))

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
        session_id = event_data.get("id")
        metadata = event_data.get("metadata", {}) or {}
        payment_id = metadata.get("payment_id")
        payment = None
        if payment_id:
            try:
                payment = db.get(models.Payment, int(payment_id))
            except (TypeError, ValueError):
                payment = None
        if not payment:
            payment = db.query(models.Payment).filter(models.Payment.provider_ref == session_id).first()
        if payment:
            payment.status = "paid"
            if payment.booking_id:
                booking = db.get(models.Booking, payment.booking_id)
                if booking:
                    booking.status = "confirmed"
            subscription_id = metadata.get("subscription_id")
            if subscription_id:
                try:
                    subscription = db.get(models.ClientSubscription, int(subscription_id))
                except (TypeError, ValueError):
                    subscription = None
                if subscription:
                    subscription.status = "active"
            db.commit()
    elif event_type == "checkout.session.expired":
        session_id = event_data.get("id")
        metadata = event_data.get("metadata", {}) or {}
        payment_id = metadata.get("payment_id")
        payment = None
        if payment_id:
            try:
                payment = db.get(models.Payment, int(payment_id))
            except (TypeError, ValueError):
                payment = None
        if not payment:
            payment = db.query(models.Payment).filter(models.Payment.provider_ref == session_id).first()
        if payment:
            payment.status = "failed"
            if payment.booking_id:
                booking = db.get(models.Booking, payment.booking_id)
                if booking and booking.status == "pending_payment":
                    booking.status = "cancelled"
            subscription_id = metadata.get("subscription_id")
            if subscription_id:
                try:
                    subscription = db.get(models.ClientSubscription, int(subscription_id))
                except (TypeError, ValueError):
                    subscription = None
                if subscription and subscription.status == "pending":
                    subscription.status = "cancelled"
            db.commit()

    return {"received": True}


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

"""Root, health, and dashboard summary routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import deps as _d
from .config import logger


def register_routes(router: APIRouter) -> None:
    @router.get("/")
    def root():
        return {"app": "Maestro Yoga", "status": "running"}

    @router.get("/health")
    def health():
        """مسار خفيف لفحص الصحة على Render وغيره (بدون اتصال بقاعدة البيانات)."""
        return {"status": "ok"}

    @router.get("/health/ready")
    def health_ready(db: Session = Depends(_d.get_db)):
        """جاهزية الخدمة مع التحقق من قاعدة البيانات (مناسب بعد النشر أو للموازن)."""
        try:
            db.execute(text("SELECT 1"))
            return {"status": "ready", "database": "ok"}
        except Exception as exc:
            logger.warning("health_ready database check failed: %s", exc)
            raise HTTPException(status_code=503, detail="database_unavailable") from exc

    @router.get("/dashboard/summary", response_model=_d.schemas.DashboardSummaryOut)
    def dashboard_summary(
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.get_current_user),
    ):
        center_id = _d.require_user_center_id(user)
        today = datetime.now(timezone.utc).date()

        clients_count = db.query(_d.models.Client).filter(_d.models.Client.center_id == center_id).count()
        sessions_count = db.query(_d.models.YogaSession).filter(_d.models.YogaSession.center_id == center_id).count()
        bookings_count = db.query(_d.models.Booking).filter(_d.models.Booking.center_id == center_id).count()
        active_plans_count = (
            db.query(_d.models.SubscriptionPlan)
            .filter(
                _d.models.SubscriptionPlan.center_id == center_id,
                _d.models.SubscriptionPlan.is_active.is_(True),
            )
            .count()
        )
        revenue_total = (
            db.query(func.coalesce(func.sum(_d.models.Payment.amount), 0.0))
            .filter(_d.models.Payment.center_id == center_id, _d.models.Payment.status == "paid")
            .scalar()
        )
        revenue_today = (
            db.query(func.coalesce(func.sum(_d.models.Payment.amount), 0.0))
            .filter(
                _d.models.Payment.center_id == center_id,
                _d.models.Payment.status == "paid",
                func.date(_d.models.Payment.paid_at) == today,
            )
            .scalar()
        )
        pending_payments_count = (
            db.query(_d.models.Payment)
            .filter(_d.models.Payment.center_id == center_id, _d.models.Payment.status == "pending")
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

"""Dashboard summary counts and paginated payment rows for the admin dashboard."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from . import impl_state as _s
from .admin_dashboard_blocks_pagination import normalize_admin_list_page


def build_dashboard_summary_dict(
    db: _s.Session,
    cid: int,
    rooms: Sequence[Any],
    sessions_total: int,
    plans: Sequence[Any],
    paid_revenue_total: float,
    paid_revenue_today: float,
    public_users_count: int,
    public_users_deleted_count: int,
    public_users_new_7d: int,
) -> dict[str, Any]:
    return {
        "rooms_count": len(rooms),
        "sessions_count": sessions_total,
        "bookings_count": db.query(_s.models.Booking).filter(_s.models.Booking.center_id == cid).count(),
        "clients_count": db.query(_s.models.Client).filter(_s.models.Client.center_id == cid).count(),
        "active_plans_count": sum(1 for p in plans if p.is_active),
        "active_subscriptions_count": (
            db.query(_s.models.ClientSubscription)
            .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
            .filter(
                _s.models.Client.center_id == cid,
                _s.models.ClientSubscription.status == "active",
            )
            .count()
        ),
        "revenue_total": float(paid_revenue_total or 0.0),
        "revenue_today": float(paid_revenue_today or 0.0),
        "public_users_count": int(public_users_count) - int(public_users_deleted_count),
        "public_users_deleted_count": int(public_users_deleted_count),
        "public_users_new_7d": int(public_users_new_7d),
    }


@dataclass(frozen=True)
class PaymentsPageBundle:
    payment_rows: list[dict[str, Any]]
    payments_total: int
    safe_payments_page: int
    payments_total_pages: int
    payments_page_size: int


def load_paginated_payment_rows(
    db: _s.Session,
    cid: int,
    payment_from_dt: Any,
    payment_to_dt: Any,
    payments_page: int,
) -> PaymentsPageBundle:
    payments_page_size = _s.ADMIN_PAYMENTS_PAGE_SIZE
    payments_base_query = db.query(_s.models.Payment).filter(_s.models.Payment.center_id == cid)
    if payment_from_dt:
        payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) >= payment_from_dt)
    if payment_to_dt:
        payments_base_query = payments_base_query.filter(_s.func.date(_s.models.Payment.paid_at) <= payment_to_dt)
    payments_total = payments_base_query.order_by(None).count()
    safe_payments_page, payments_total_pages, payments_offset = normalize_admin_list_page(
        payments_page,
        payments_total,
        payments_page_size,
    )
    recent_payments = (
        payments_base_query.order_by(_s.models.Payment.paid_at.desc())
        .offset(payments_offset)
        .limit(payments_page_size)
        .all()
    )
    client_ids = [p.client_id for p in recent_payments]
    clients_by_id = {
        c.id: c
        for c in db.query(_s.models.Client).filter(_s.models.Client.id.in_(client_ids)).all()
    }
    status_labels = {
        "paid": "مدفوع",
        "pending": "قيد الانتظار",
        "failed": "فشل",
    }
    payment_rows = []
    for pay in recent_payments:
        client = clients_by_id.get(pay.client_id)
        payment_rows.append(
            {
                "id": pay.id,
                "client_name": client.full_name if client else f"عميل #{pay.client_id}",
                "payment_method": pay.payment_method,
                "amount": pay.amount,
                "currency": pay.currency,
                "status": pay.status,
                "status_label": status_labels.get(pay.status, pay.status),
                "paid_at_display": _s._fmt_dt(pay.paid_at),
            }
        )
    return PaymentsPageBundle(
        payment_rows=payment_rows,
        payments_total=payments_total,
        safe_payments_page=safe_payments_page,
        payments_total_pages=payments_total_pages,
        payments_page_size=payments_page_size,
    )

"""Admin dashboard KPI counter queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import impl_state as _s


@dataclass(frozen=True)
class AdminKpiCounts:
    sessions_today_no_bookings: int
    subs_expiring_7d: int
    pending_payments_stale_8d: int
    failed_payments_7d: int
    sessions_scheduled_today: int
    bookings_active_today: int
    public_users_unverified_count: int


def fetch_admin_kpi_counts(db: _s.Session, cid: int, today: Any, now_na: Any) -> AdminKpiCounts:
    sessions_today_no_bookings = (
        db.query(_s.models.YogaSession.id)
        .outerjoin(
            _s.models.Booking,
            _s.and_(
                _s.models.Booking.session_id == _s.models.YogaSession.id,
                _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
            ),
        )
        .filter(
            _s.models.YogaSession.center_id == cid,
            _s.func.date(_s.models.YogaSession.starts_at) == today,
        )
        .group_by(_s.models.YogaSession.id)
        .having(_s.func.count(_s.models.Booking.id) == 0)
        .count()
    )
    subs_expiring_7d = (
        db.query(_s.models.ClientSubscription)
        .join(_s.models.Client, _s.models.Client.id == _s.models.ClientSubscription.client_id)
        .filter(
            _s.models.Client.center_id == cid,
            _s.models.ClientSubscription.status == "active",
            _s.models.ClientSubscription.end_date >= now_na,
            _s.models.ClientSubscription.end_date <= now_na + _s.timedelta(days=7),
        )
        .count()
    )
    pending_cutoff = now_na - _s.timedelta(days=8)
    pending_payments_stale_8d = int(
        db.query(_s.func.count(_s.models.Payment.id))
        .filter(
            _s.models.Payment.center_id == cid,
            _s.models.Payment.status.in_(("pending", "pending_payment")),
            _s.func.coalesce(_s.models.Payment.created_at, _s.models.Payment.paid_at) <= pending_cutoff,
        )
        .scalar()
        or 0
    )
    failed_payments_7d = int(
        db.query(_s.func.count(_s.models.Payment.id))
        .filter(
            _s.models.Payment.center_id == cid,
            _s.models.Payment.status == "failed",
            _s.func.date(_s.models.Payment.paid_at) >= today - _s.timedelta(days=7),
            _s.func.date(_s.models.Payment.paid_at) <= today,
        )
        .scalar()
        or 0
    )
    sessions_scheduled_today = int(
        db.query(_s.func.count(_s.models.YogaSession.id))
        .filter(_s.models.YogaSession.center_id == cid, _s.func.date(_s.models.YogaSession.starts_at) == today)
        .scalar()
        or 0
    )
    bookings_active_today = int(
        db.query(_s.func.count(_s.models.Booking.id))
        .join(_s.models.YogaSession, _s.models.YogaSession.id == _s.models.Booking.session_id)
        .filter(
            _s.models.YogaSession.center_id == cid,
            _s.func.date(_s.models.YogaSession.starts_at) == today,
            _s.models.Booking.status.in_(_s.ACTIVE_BOOKING_STATUSES),
        )
        .scalar()
        or 0
    )
    public_users_unverified_count = (
        _s._public_users_query_for_center(db, cid)
        .filter(
            _s.models.PublicUser.is_deleted.is_(False),
            _s.models.PublicUser.is_active.is_(True),
            _s.models.PublicUser.email_verified.is_(False),
        )
        .count()
    )
    return AdminKpiCounts(
        sessions_today_no_bookings=sessions_today_no_bookings,
        subs_expiring_7d=subs_expiring_7d,
        pending_payments_stale_8d=pending_payments_stale_8d,
        failed_payments_7d=failed_payments_7d,
        sessions_scheduled_today=sessions_scheduled_today,
        bookings_active_today=bookings_active_today,
        public_users_unverified_count=public_users_unverified_count,
    )

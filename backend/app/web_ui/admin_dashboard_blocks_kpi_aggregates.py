"""Admin login audit rows and paid revenue / public-user rollups."""

from __future__ import annotations

from typing import Any

from . import impl_state as _s


def fetch_admin_login_audit_rows(db: _s.Session) -> list[dict[str, str]]:
    return [
        {
            "created_at_display": _s._fmt_dt(ev.created_at),
            "status": ev.status,
            "email": ev.email or "-",
            "ip": ev.ip or "-",
        }
        for ev in db.query(_s.models.SecurityAuditEvent)
        .filter(_s.models.SecurityAuditEvent.event_type == "admin_login")
        .order_by(_s.models.SecurityAuditEvent.created_at.desc())
        .limit(20)
        .all()
    ]


def aggregate_paid_revenue_and_public_user_stats(
    db: _s.Session, cid: int, today: Any
) -> tuple[float, float, int, int, int]:
    recent_public_cutoff = _s.utcnow_naive() - _s.timedelta(days=7)
    paid_revenue_total, paid_revenue_today = (
        db.query(
            _s.func.coalesce(
                _s.func.sum(
                    _s.case(
                        (_s.models.Payment.status == "paid", _s.models.Payment.amount),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
            _s.func.coalesce(
                _s.func.sum(
                    _s.case(
                        (
                            _s.and_(
                                _s.models.Payment.status == "paid",
                                _s.func.date(_s.models.Payment.paid_at) == today,
                            ),
                            _s.models.Payment.amount,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
        )
        .filter(_s.models.Payment.center_id == cid)
        .one()
    )
    scoped_public_users = _s._public_users_query_for_center(db, cid).subquery()
    public_users_count, public_users_deleted_count, public_users_new_7d = (
        db.query(
            _s.func.count(scoped_public_users.c.id),
            _s.func.coalesce(
                _s.func.sum(_s.case((scoped_public_users.c.is_deleted.is_(True), 1), else_=0)),
                0,
            ),
            _s.func.coalesce(
                _s.func.sum(
                    _s.case(
                        (
                            _s.and_(
                                scoped_public_users.c.created_at >= recent_public_cutoff,
                                scoped_public_users.c.is_deleted.is_(False),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).one()
    )
    return (
        float(paid_revenue_total or 0.0),
        float(paid_revenue_today or 0.0),
        int(public_users_count),
        int(public_users_deleted_count),
        int(public_users_new_7d),
    )

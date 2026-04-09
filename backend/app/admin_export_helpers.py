import csv
import io
from datetime import date, datetime


def clients_new_returning_for_range(
    *,
    db,
    models_module,
    center_id: int,
    d0: date,
    d1: date,
    active_booking_statuses,
    func_module,
) -> tuple[int, int, int]:
    sess_filters = [
        models_module.YogaSession.center_id == center_id,
        func_module.date(models_module.YogaSession.starts_at) >= d0,
        func_module.date(models_module.YogaSession.starts_at) <= d1,
    ]
    active_client_ids = (
        db.query(models_module.Booking.client_id)
        .join(models_module.YogaSession, models_module.YogaSession.id == models_module.Booking.session_id)
        .filter(*sess_filters, models_module.Booking.status.in_(active_booking_statuses))
        .distinct()
        .all()
    )
    cids_period = [r[0] for r in active_client_ids]
    first_dates: dict[int, date] = {}
    if cids_period:
        for cid_row, fst in (
            db.query(models_module.Booking.client_id, func_module.min(models_module.Booking.booked_at))
            .filter(models_module.Booking.center_id == center_id, models_module.Booking.client_id.in_(cids_period))
            .group_by(models_module.Booking.client_id)
            .all()
        ):
            if fst:
                first_dates[cid_row] = fst.date() if isinstance(fst, datetime) else fst
    new_clients = 0
    returning_clients = 0
    for cl_id in set(cids_period):
        fd = first_dates.get(cl_id)
        if not fd:
            continue
        if d0 <= fd <= d1:
            new_clients += 1
        else:
            returning_clients += 1
    distinct_booking_clients = len(set(cids_period))
    return new_clients, returning_clients, distinct_booking_clients


def admin_user_for_export_permission(
    *,
    request,
    db,
    permission_id: str,
    require_admin_user_or_redirect_fn,
    user_has_permission_fn,
    forbidden_redirect_fn,
):
    user, redirect = require_admin_user_or_redirect_fn(request, db)
    if redirect:
        return None, redirect
    assert user is not None
    if not user_has_permission_fn(user, permission_id):
        return None, forbidden_redirect_fn()
    return user, None


def build_bookings_csv_content(rows) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "booking_id",
            "status",
            "booked_at",
            "session_id",
            "session_title",
            "session_starts_at",
            "client_id",
            "client_name",
            "client_email",
        ]
    )
    for bk, sess, cl in rows:
        writer.writerow(
            [
                bk.id,
                bk.status,
                bk.booked_at.isoformat() if bk.booked_at else "",
                sess.id,
                sess.title,
                sess.starts_at.isoformat() if sess.starts_at else "",
                cl.id,
                cl.full_name,
                cl.email,
            ]
        )
    content = output.getvalue()
    output.close()
    return content


def build_payments_csv_content(*, rows, clients_map) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["payment_id", "client_id", "client_name", "amount", "currency", "status", "method", "paid_at", "booking_id"])
    for p in rows:
        cl = clients_map.get(p.client_id)
        writer.writerow(
            [
                p.id,
                p.client_id,
                cl.full_name if cl else "",
                p.amount,
                p.currency,
                p.status,
                p.payment_method,
                p.paid_at.isoformat() if p.paid_at else "",
                p.booking_id or "",
            ]
        )
    content = output.getvalue()
    output.close()
    return content


def build_security_events_csv_content(events) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "event_type", "status", "email", "ip", "path", "details_json"])
    for ev in events:
        writer.writerow(
            [
                ev.id,
                ev.created_at.isoformat() if ev.created_at else "",
                ev.event_type,
                ev.status,
                ev.email or "",
                ev.ip or "",
                ev.path or "",
                ev.details_json or "",
            ]
        )
    content = output.getvalue()
    output.close()
    return content

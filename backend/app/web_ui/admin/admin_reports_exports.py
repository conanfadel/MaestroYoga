"""Admin CSV export routes — registered on shared web UI router."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import models
from ...admin_export_helpers import (
    admin_user_for_export_permission,
    build_bookings_csv_content,
    build_payments_csv_content,
    build_security_events_csv_content,
    build_security_events_filtered_query,
)
from ...admin_report_helpers import utf8_bom_csv_content
from ...database import get_db
from ...rbac import user_has_permission
from ...tenant_utils import require_user_center_id
from ...time_utils import utcnow_naive


def register_admin_report_exports(router: APIRouter) -> None:
    from .. import impl_state as core

    @router.get("/admin/export/clients.csv")
    def export_clients_csv(request: Request, db: Session = Depends(get_db)):
        user, redirect = admin_user_for_export_permission(
            request=request,
            db=db,
            permission_id="exports.clients",
            require_admin_user_or_redirect_fn=core._require_admin_user_or_redirect,
            user_has_permission_fn=user_has_permission,
            forbidden_redirect_fn=core._trainer_forbidden_redirect,
        )
        if redirect:
            return redirect
        assert user is not None
        cid = require_user_center_id(user)
        rows = (
            db.query(models.Client)
            .filter(models.Client.center_id == cid)
            .order_by(models.Client.created_at.desc())
            .all()
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "full_name", "email", "phone", "created_at"])
        for c in rows:
            writer.writerow(
                [
                    c.id,
                    c.full_name,
                    c.email,
                    c.phone or "",
                    c.created_at.isoformat() if c.created_at else "",
                ]
            )
        content = utf8_bom_csv_content(output)
        output.close()
        fn = f"clients_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([content]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fn}"'},
        )


    @router.get("/admin/export/bookings.csv")
    def export_bookings_csv(request: Request, db: Session = Depends(get_db)):
        user, redirect = admin_user_for_export_permission(
            request=request,
            db=db,
            permission_id="exports.bookings",
            require_admin_user_or_redirect_fn=core._require_admin_user_or_redirect,
            user_has_permission_fn=user_has_permission,
            forbidden_redirect_fn=core._trainer_forbidden_redirect,
        )
        if redirect:
            return redirect
        assert user is not None
        cid = require_user_center_id(user)
        q = (
            db.query(models.Booking, models.YogaSession, models.Client)
            .join(models.YogaSession, models.YogaSession.id == models.Booking.session_id)
            .join(models.Client, models.Client.id == models.Booking.client_id)
            .filter(models.Booking.center_id == cid)
            .order_by(models.Booking.booked_at.desc())
            .limit(50_000)
            .all()
        )
        content = utf8_bom_csv_content(io.StringIO(build_bookings_csv_content(q)))
        fn = f"bookings_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([content]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fn}"'},
        )


    @router.get("/admin/export/payments.csv")
    def export_payments_csv(
        request: Request,
        payment_date_from: str = "",
        payment_date_to: str = "",
        db: Session = Depends(get_db),
    ):
        user, redirect = admin_user_for_export_permission(
            request=request,
            db=db,
            permission_id="exports.payments",
            require_admin_user_or_redirect_fn=core._require_admin_user_or_redirect,
            user_has_permission_fn=user_has_permission,
            forbidden_redirect_fn=core._trainer_forbidden_redirect,
        )
        if redirect:
            return redirect
        assert user is not None
        cid = require_user_center_id(user)
        pq = db.query(models.Payment).filter(models.Payment.center_id == cid)
        pdf = core._parse_optional_date_str(payment_date_from)
        pdt = core._parse_optional_date_str(payment_date_to)
        if pdf:
            pq = pq.filter(func.date(models.Payment.paid_at) >= pdf)
        if pdt:
            pq = pq.filter(func.date(models.Payment.paid_at) <= pdt)
        rows = pq.order_by(models.Payment.paid_at.desc()).limit(50_000).all()
        client_ids = list({p.client_id for p in rows})
        clients_map = {
            c.id: c
            for c in db.query(models.Client).filter(models.Client.id.in_(client_ids)).all()
        } if client_ids else {}
        content = utf8_bom_csv_content(
            io.StringIO(
                build_payments_csv_content(
                    rows=rows,
                    clients_map=clients_map,
                )
            )
        )
        fn = f"payments_center_{cid}_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([content]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fn}"'},
        )


    @router.get("/admin/security/export/csv")
    def export_security_events_csv(
        request: Request,
        audit_event_type: str = "",
        audit_status: str = "",
        audit_email: str = "",
        audit_ip: str = "",
        audit_date_from: str = "",
        audit_date_to: str = "",
        db: Session = Depends(get_db),
    ):
        user, redirect = core._require_admin_user_or_redirect(request, db)
        if redirect:
            return redirect
        assert user is not None
        if not user_has_permission(user, "security.audit"):
            return core._security_owner_forbidden_redirect()

        query = build_security_events_filtered_query(
            db=db,
            models_module=models,
            func_module=func,
            parse_optional_date_fn=core._parse_optional_date_str,
            audit_event_type=audit_event_type,
            audit_status=audit_status,
            audit_email=audit_email,
            audit_ip=audit_ip,
            audit_date_from=audit_date_from,
            audit_date_to=audit_date_to,
        )
        events = query.order_by(models.SecurityAuditEvent.created_at.desc()).all()

        filename = f"security_audit_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        content = build_security_events_csv_content(events)
        return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers=headers)


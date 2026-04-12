"""Payment creation, checkout session, listing, and export routes."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from . import deps as _d
from .config import logger
from .helpers import is_checkout_redirect_allowed, payments_query


def register_routes(router: APIRouter) -> None:
    @router.post("/payments", response_model=_d.schemas.PaymentOut)
    def create_payment(
        payload: _d.schemas.PaymentCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("payments.records", "payments.refund")),
    ):
        center_id = _d.require_user_center_id(user)
        client = db.get(_d.models.Client, payload.client_id)
        if not client or client.center_id != center_id:
            raise HTTPException(status_code=404, detail="Client not found for center")

        provider = _d.get_payment_provider()
        if _d.payment_provider_supports_hosted_checkout(provider):
            raise HTTPException(
                status_code=400,
                detail="Use /payments/checkout-session for Stripe or Paymob payments",
            )
        provider_result = provider.charge(
            amount=payload.amount,
            currency=payload.currency,
            metadata={"center_id": center_id, "client_id": payload.client_id},
        )

        payment = _d.models.Payment(
            center_id=center_id,
            booking_id=None,
            **payload.model_dump(),
            provider_ref=provider_result.provider_ref,
            status=provider_result.status,
            created_at=_d.utcnow_naive(),
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
        return payment

    @router.post("/payments/checkout-session", response_model=_d.schemas.PaymentCheckoutOut)
    def create_checkout_session(
        payload: _d.schemas.PaymentCheckoutCreate,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("payments.records", "payments.refund")),
    ):
        center_id = _d.require_user_center_id(user)
        client = db.get(_d.models.Client, payload.client_id)
        if not client or client.center_id != center_id:
            raise HTTPException(status_code=404, detail="Client not found for center")

        provider = _d.get_payment_provider()
        if not _d.payment_provider_supports_hosted_checkout(provider):
            raise HTTPException(status_code=400, detail="Checkout session requires Stripe or Paymob provider")
        if not is_checkout_redirect_allowed(payload.success_url) or not is_checkout_redirect_allowed(
            payload.cancel_url
        ):
            raise HTTPException(
                status_code=400,
                detail="success_url/cancel_url must match allowed checkout origins",
            )

        pm = "paymob_checkout" if isinstance(provider, _d.PaymobPaymentProvider) else "stripe_checkout"
        payment = _d.models.Payment(
            center_id=center_id,
            client_id=payload.client_id,
            booking_id=None,
            amount=payload.amount,
            currency=payload.currency.upper(),
            payment_method=pm,
            status="pending",
            created_at=_d.utcnow_naive(),
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
            logger.exception("Failed to create hosted checkout session: %s", exc)
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

    @router.get("/payments/{payment_id}", response_model=_d.schemas.PaymentOut)
    def get_payment_status(
        payment_id: int,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(
            _d.require_any_permission("payments.records", "reports.financial", "exports.payments")
        ),
    ):
        center_id = _d.require_user_center_id(user)
        payment = db.get(_d.models.Payment, payment_id)
        if not payment or payment.center_id != center_id:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment

    @router.get("/payments", response_model=list[_d.schemas.PaymentOut])
    def list_payments(
        client_id: int | None = None,
        status: str | None = None,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("payments.records", "reports.financial")),
    ):
        center_id = _d.require_user_center_id(user)
        query = payments_query(db, center_id=center_id, client_id=client_id, status=status)
        return query.order_by(_d.models.Payment.paid_at.desc()).all()

    @router.get("/payments/export/csv")
    def export_payments_csv(
        client_id: int | None = None,
        status: str | None = None,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("exports.payments", "reports.financial")),
    ):
        center_id = _d.require_user_center_id(user)
        query = payments_query(db, center_id=center_id, client_id=client_id, status=status)

        payments = query.order_by(_d.models.Payment.paid_at.desc()).all()

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

    @router.get("/payments/export/xlsx")
    def export_payments_xlsx(
        client_id: int | None = None,
        status: str | None = None,
        db: Session = Depends(_d.get_db),
        user: _d.models.User = Depends(_d.require_any_permission("exports.payments", "reports.financial")),
    ):
        center_id = _d.require_user_center_id(user)
        query = payments_query(db, center_id=center_id, client_id=client_id, status=status)
        payments = query.order_by(_d.models.Payment.paid_at.desc()).all()

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
        hdrs = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=hdrs,
        )

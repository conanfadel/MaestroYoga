"""Public payment receipt page (print-friendly)."""

from __future__ import annotations

from fastapi import APIRouter

from ...checkout_status_urls import parse_payment_ids_param, verify_checkout_status_signature
from .. import impl_state as _s


def register_public_payment_receipt_routes(router: APIRouter) -> None:
    @router.get("/public/payment-receipt", response_class=_s.HTMLResponse)
    def public_payment_receipt(
        request: _s.Request,
        center_id: int | None = _s.Query(default=None),
        payment_id: int | None = _s.Query(default=None),
        payment_ids: str | None = _s.Query(default=None),
        sig: str | None = _s.Query(default=None),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        ctx: dict = {
            "valid_link": False,
            "headline": "إيصال غير صالح",
            "body": "تعذر التحقق من رابط الإيصال.",
            "rows": [],
            "total_amount": 0.0,
            "currency": "SAR",
            "index_href": "/index",
            "account_href": "/public/account",
            "generated_at": _s._fmt_dt(_s.utcnow_naive()),
        }
        if center_id is None or center_id < 1:
            return _s.templates.TemplateResponse(request, "public_payment_receipt.html", ctx)
        parsed = parse_payment_ids_param(payment_id=payment_id, payment_ids_raw=payment_ids)
        if not parsed or not sig or not verify_checkout_status_signature(center_id, parsed, sig):
            return _s.templates.TemplateResponse(request, "public_payment_receipt.html", ctx)

        rows = (
            db.query(_s.models.Payment)
            .filter(
                _s.models.Payment.center_id == int(center_id),
                _s.models.Payment.id.in_(parsed),
            )
            .order_by(_s.models.Payment.id.asc())
            .all()
        )
        if not rows:
            return _s.templates.TemplateResponse(request, "public_payment_receipt.html", ctx)

        items: list[dict[str, str]] = []
        total = 0.0
        cur = str(rows[0].currency or "SAR")
        for p in rows:
            booking_title = "-"
            booking_time = "-"
            if p.booking_id:
                b = db.get(_s.models.Booking, p.booking_id)
                ys = db.get(_s.models.YogaSession, b.session_id) if b else None
                if ys:
                    booking_title = str(ys.title or "جلسة")
                    booking_time = _s._fmt_dt(ys.starts_at)
            total += float(p.amount or 0.0)
            items.append(
                {
                    "payment_id": str(int(p.id)),
                    "provider_ref": str(p.provider_ref or "-"),
                    "status": str(p.status or "-"),
                    "session_title": booking_title,
                    "session_time": booking_time,
                    "amount": f"{float(p.amount or 0.0):.2f}",
                    "paid_at": _s._fmt_dt(p.paid_at),
                }
            )

        ctx.update(
            {
                "valid_link": True,
                "headline": "إيصال الدفع",
                "body": "تم إصدار إيصال موحد للعمليات المرتبطة بهذا الطلب.",
                "rows": items,
                "total_amount": f"{total:.2f}",
                "currency": cur,
                "index_href": f"/index?center_id={int(center_id)}",
                "account_href": _s._url_with_params("/public/account", center_id=str(int(center_id))),
            }
        )
        return _s.templates.TemplateResponse(request, "public_payment_receipt.html", ctx)

"""صفحة حالة الدفع بعد العودة من بوابة الدفع (Paymob / Stripe)."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter

from ...checkout_status_urls import parse_payment_ids_param, verify_checkout_status_signature
from .. import impl_state as _s

# Paymob يُلحق حقولاً كثيرة على redirection_url — نُبقي الموقّع + success (رفض فوري دون انتظار webhook).
_CHECKOUT_STATUS_QUERY_KEEP = frozenset(
    {"center_id", "payment_id", "payment_ids", "sig", "result", "flow", "session_id", "success"}
)


def _query_bool_false(raw: str | None) -> bool:
    s = (raw or "").strip().lower()
    return s in ("false", "0", "no", "off")


def _paymob_redirect_claims_payment_failed(request: _s.Request) -> bool:
    return _query_bool_false(request.query_params.get("success"))


def _maybe_redirect_clean_checkout_status_query(request: _s.Request) -> _s.RedirectResponse | None:
    qp = request.query_params
    if not qp:
        return None
    if set(qp.keys()) <= _CHECKOUT_STATUS_QUERY_KEEP:
        return None
    if not qp.get("sig"):
        return None
    pairs: list[tuple[str, str]] = []
    for name in sorted(_CHECKOUT_STATUS_QUERY_KEEP):
        if name not in qp:
            continue
        v = qp.get(name)
        if v is not None and str(v).strip() != "":
            pairs.append((name, str(v).strip()))
    if not pairs:
        return None
    return _s.RedirectResponse(url="/checkout-status?" + urlencode(pairs), status_code=303)


def register_public_checkout_status_routes(router: APIRouter) -> None:
    @router.get("/checkout-status", response_class=_s.HTMLResponse)
    def public_checkout_status(
        request: _s.Request,
        center_id: int | None = _s.Query(default=None),
        payment_id: int | None = _s.Query(default=None),
        payment_ids: str | None = _s.Query(default=None),
        sig: str | None = _s.Query(default=None),
        result: str | None = _s.Query(default=None),
        flow: str | None = _s.Query(default=None),
        db: _s.Session = _s.Depends(_s.get_db),
    ):
        early = _maybe_redirect_clean_checkout_status_query(request)
        if early is not None:
            return early

        ctx: dict = {
            "center_id": center_id,
            "valid_link": False,
            "status_kind": "invalid",
            "headline": "رابط غير صالح",
            "body": "تأكد أنك فتحت الرابط من نفس الجلسة التي بدأت منها الدفع.",
            "index_href": "/index",
            "refresh_pending": False,
            "cancel_requested": bool((result or "").strip().lower() == "cancelled"),
            "subscription_flow": bool((flow or "").strip().lower() == "subscription"),
        }

        if center_id is None or center_id < 1:
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        parsed = parse_payment_ids_param(payment_id=payment_id, payment_ids_raw=payment_ids)
        if not parsed or not sig:
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        if not verify_checkout_status_signature(center_id, parsed, sig):
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        rows = (
            db.query(_s.models.Payment)
            .filter(
                _s.models.Payment.center_id == int(center_id),
                _s.models.Payment.id.in_(parsed),
            )
            .all()
        )
        if len(rows) != len(parsed):
            ctx["body"] = "تعذّر العثور على بيانات الدفع المرتبطة بهذا الرابط."
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        statuses = [str(getattr(p, "status", "") or "").lower() for p in rows]
        paid_all = all(s == "paid" for s in statuses)
        failed_all = all(s == "failed" for s in statuses)
        pending_any = any(s == "pending" for s in statuses)
        paymob_declined = _paymob_redirect_claims_payment_failed(request)

        ctx["valid_link"] = True
        ctx["index_href"] = f"/index?center_id={int(center_id)}"

        if ctx["cancel_requested"]:
            if paid_all:
                pass
            else:
                ctx["status_kind"] = "cancelled"
                ctx["headline"] = "تم إلغاء الدفع"
                ctx["body"] = (
                    "لم يُكمَل الدفع من البوابة. إذا ظهر خصم مؤقت على البطاقة فغالباً يُعاد خلال أيام عمل حسب البنك."
                )
                if pending_any and not paymob_declined:
                    ctx["body"] += (
                        " حالة الطلب في نظامنا: قيد الانتظار — قد تتحدّث خلال ثوانٍ بعد إشعار البوابة."
                    )
                    ctx["refresh_pending"] = True
                elif pending_any and paymob_declined:
                    ctx["body"] += (
                        " البوابة أبلغت برفض العملية؛ قد يبقى السجل قيد الانتظار لحظات حتى يصل الإشعار."
                    )
                elif failed_all:
                    ctx["body"] = (
                        "تم تسجيل الفشل في نظامنا. يمكنك المحاولة من جديد من صفحة الحجز أو الاشتراك."
                    )
                return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        if paid_all:
            ctx["status_kind"] = "paid"
            if ctx["subscription_flow"]:
                ctx["headline"] = "تم الاشتراك بنجاح"
                ctx["body"] = "شكراً لك. تم تفعيل الاشتراك في النظام."
            else:
                ctx["headline"] = "تم الدفع بنجاح"
                ctx["body"] = "شكراً لك. تم تأكيد الدفع في النظام."
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        if failed_all:
            ctx["status_kind"] = "failed"
            ctx["headline"] = "لم يُقبل الدفع"
            ctx["body"] = "لم نستلم تأكيداً بنجاح من بوابة الدفع. يمكنك إعادة المحاولة."
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        if pending_any:
            if paymob_declined:
                ctx["status_kind"] = "declined_redirect"
                ctx["headline"] = "لم يُقبل الدفع"
                ctx["body"] = (
                    "أبلغت بوابة الدفع أن العملية لم تُكتمل (مرفوضة أو غير مصرّح بها). "
                    "لم نعد نحدّث الصفحة تلقائياً. إذا بقي السجل «قيد الانتظار» في نظامنا فسيُحدَّث عند وصول إشعار البوابة."
                )
                ctx["refresh_pending"] = False
            else:
                ctx["status_kind"] = "pending"
                ctx["headline"] = "جاري تأكيد الدفع"
                ctx["body"] = (
                    "ننتظر إشعار البوابة (Webhook). قد يستغرق ذلك بضع ثوانٍ — سيتم تحديث الصفحة تلقائياً."
                )
                ctx["refresh_pending"] = True
            return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

        ctx["status_kind"] = "mixed"
        ctx["headline"] = "حالة مختلطة"
        ctx["body"] = "توجد مدفوعات بحالات مختلفة. تواصل مع المركز إن استمرّ الغموض."
        return _s.templates.TemplateResponse(request, "checkout_status.html", ctx)

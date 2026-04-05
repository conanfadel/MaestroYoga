import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional
from uuid import uuid4

import stripe


@dataclass
class PaymentResult:
    provider_ref: str
    status: str
    checkout_url: Optional[str] = None


class BasePaymentProvider:
    def charge(self, amount: float, currency: str, metadata: dict) -> PaymentResult:
        raise NotImplementedError

    def create_checkout_session(
        self,
        amount: float,
        currency: str,
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
        *,
        line_item_name: str = "Maestro Yoga",
        line_item_description: str = "",
    ) -> PaymentResult:
        raise NotImplementedError

    def create_checkout_session_multi_line(
        self,
        currency: str,
        line_specs: list[tuple[float, str, str]],
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        raise NotImplementedError


class MockPaymentProvider(BasePaymentProvider):
    def charge(self, amount: float, currency: str, metadata: dict) -> PaymentResult:
        return PaymentResult(provider_ref=f"mock_{uuid4().hex[:12]}", status="paid")

    def create_checkout_session(
        self,
        amount: float,
        currency: str,
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
        *,
        line_item_name: str = "Maestro Yoga",
        line_item_description: str = "",
    ) -> PaymentResult:
        return PaymentResult(
            provider_ref=f"mock_checkout_{uuid4().hex[:12]}",
            status="paid",
            checkout_url=success_url,
        )

    def create_checkout_session_multi_line(
        self,
        currency: str,
        line_specs: list[tuple[float, str, str]],
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        return PaymentResult(
            provider_ref=f"mock_cart_{uuid4().hex[:12]}",
            status="paid",
            checkout_url=success_url,
        )


class StripePaymentProvider(BasePaymentProvider):
    def __init__(self) -> None:
        secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured")
        stripe.api_key = secret_key

    def charge(self, amount: float, currency: str, metadata: dict) -> PaymentResult:
        # Stripe production flow should use checkout-session endpoint.
        return PaymentResult(provider_ref=f"stripe_manual_{uuid4().hex[:10]}", status="pending")

    def create_checkout_session(
        self,
        amount: float,
        currency: str,
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
        *,
        line_item_name: str = "Maestro Yoga",
        line_item_description: str = "",
    ) -> PaymentResult:
        """
        Checkout بالبطاقة (SAR). لحساب Stripe مسجّل في السعودية تُقبل بطاقات **مدى**
        ضمن نموذج البطاقة نفسه — راجع توثيق Stripe لمادا.
        """
        locale = os.getenv("STRIPE_CHECKOUT_LOCALE", "auto").strip() or "auto"
        product_data: dict[str, Any] = {"name": (line_item_name or "Maestro Yoga")[:120]}
        desc = (line_item_description or "").strip()
        if desc:
            product_data["description"] = desc[:500]

        create_kwargs: dict[str, Any] = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items": [
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": product_data,
                        "unit_amount": int(round(amount * 100)),
                    },
                    "quantity": 1,
                }
            ],
            "metadata": metadata,
        }
        if locale.lower() != "auto":
            create_kwargs["locale"] = locale

        session = stripe.checkout.Session.create(**create_kwargs)
        return PaymentResult(provider_ref=session.id, status="pending", checkout_url=session.url)

    def create_checkout_session_multi_line(
        self,
        currency: str,
        line_specs: list[tuple[float, str, str]],
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        if not line_specs:
            raise ValueError("line_specs required")
        locale = os.getenv("STRIPE_CHECKOUT_LOCALE", "auto").strip() or "auto"
        line_items: list[dict[str, Any]] = []
        for amount, name, description in line_specs:
            product_data: dict[str, Any] = {"name": (name or "Maestro Yoga")[:120]}
            desc = (description or "").strip()
            if desc:
                product_data["description"] = desc[:500]
            line_items.append(
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": product_data,
                        "unit_amount": int(round(float(amount) * 100)),
                    },
                    "quantity": 1,
                }
            )
        create_kwargs: dict[str, Any] = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items": line_items,
            "metadata": metadata,
        }
        if locale.lower() != "auto":
            create_kwargs["locale"] = locale
        session = stripe.checkout.Session.create(**create_kwargs)
        return PaymentResult(provider_ref=session.id, status="pending", checkout_url=session.url)

    @staticmethod
    def construct_event(payload: bytes, sig_header: str) -> stripe.Event:
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)


class MoyasarPaymentProvider(BasePaymentProvider):
    """ميسر: فواتير إلكترونية مع صفحة دفع مستضافة (مدى / فيزا / ماستركارد وغيرها)."""

    API_BASE = "https://api.moyasar.com/v1"

    def __init__(self) -> None:
        self._secret = os.getenv("MOYASAR_SECRET_KEY", "").strip()
        if not self._secret:
            raise RuntimeError("MOYASAR_SECRET_KEY is not configured")

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self._secret}:".encode()).decode()
        return f"Basic {token}"

    def _request_json(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        url = f"{self.API_BASE}{path}"
        headers = {"Authorization": self._auth_header(), "Accept": "application/json"}
        data: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"moyasar_http_{exc.code}:{err_body[:400]}") from exc

    @classmethod
    def fetch_invoice(cls, invoice_id: str) -> dict[str, Any]:
        """جلب الفاتورة من API (للتحقق بعد الإشعار). يتطلب MOYASAR_SECRET_KEY في البيئة."""
        prov = cls()
        return prov._request_json("GET", f"/invoices/{invoice_id.strip()}")

    def _sar_to_halalas(self, amount: float) -> int:
        h = int(round(float(amount) * 100))
        if h < 100:
            raise RuntimeError("moyasar_min_amount: المبلغ يجب أن يكون 1 ريال أو أكثر (حد ميسر للفواتير).")
        return h

    def _string_metadata(self, metadata: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in metadata.items():
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            out[str(k)[:80]] = s[:500]
        return out

    @staticmethod
    def _moyasar_callback_url() -> str:
        base_cb = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not base_cb:
            raise RuntimeError("PUBLIC_BASE_URL is required for Moyasar callback_url")
        return f"{base_cb}/payments/webhook/moyasar"

    def _create_invoice(
        self,
        *,
        amount_halalas: int,
        description: str,
        metadata: dict[str, Any],
        success_url: str,
        back_url: str,
        callback_url: str,
    ) -> PaymentResult:
        desc = (description or "Maestro Yoga").strip()[:500] or "Maestro Yoga"
        body: dict[str, Any] = {
            "amount": amount_halalas,
            "currency": "SAR",
            "description": desc,
            "success_url": success_url,
            "back_url": back_url,
            "callback_url": callback_url,
            "metadata": self._string_metadata(metadata),
        }
        inv = self._request_json("POST", "/invoices", body)
        inv_id = inv.get("id")
        checkout_url = inv.get("url") or ""
        if not inv_id or not checkout_url:
            raise RuntimeError(f"moyasar_invalid_invoice_response:{json.dumps(inv)[:300]}")
        return PaymentResult(provider_ref=str(inv_id), status="pending", checkout_url=checkout_url)

    def create_checkout_session(
        self,
        amount: float,
        currency: str,
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
        *,
        line_item_name: str = "Maestro Yoga",
        line_item_description: str = "",
    ) -> PaymentResult:
        _ = currency
        callback_url = self._moyasar_callback_url()
        halalas = self._sar_to_halalas(amount)
        desc = f"{line_item_name} — {line_item_description}".strip()[:500] or line_item_name
        return self._create_invoice(
            amount_halalas=halalas,
            description=desc,
            metadata=metadata,
            success_url=success_url,
            back_url=cancel_url,
            callback_url=callback_url,
        )

    def create_checkout_session_multi_line(
        self,
        currency: str,
        line_specs: list[tuple[float, str, str]],
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
    ) -> PaymentResult:
        _ = currency
        if not line_specs:
            raise ValueError("line_specs required")
        callback_url = self._moyasar_callback_url()
        total = 0.0
        parts: list[str] = []
        for amt, name, description in line_specs:
            total += float(amt)
            line = f"{name}: {float(amt):.2f} SAR"
            if (description or "").strip():
                line += f" ({description.strip()[:80]})"
            parts.append(line)
        halalas = self._sar_to_halalas(total)
        desc = " | ".join(parts)[:500]
        return self._create_invoice(
            amount_halalas=halalas,
            description=desc,
            metadata=metadata,
            success_url=success_url,
            back_url=cancel_url,
            callback_url=callback_url,
        )

    def charge(self, amount: float, currency: str, metadata: dict) -> PaymentResult:
        _ = (amount, currency, metadata)
        raise NotImplementedError("Moyasar uses hosted invoice checkout only")


def get_payment_provider() -> BasePaymentProvider:
    provider = os.getenv("PAYMENT_PROVIDER", "mock").lower()
    if provider == "stripe":
        return StripePaymentProvider()
    if provider == "moyasar":
        return MoyasarPaymentProvider()
    return MockPaymentProvider()


def payment_provider_supports_hosted_checkout(provider: BasePaymentProvider) -> bool:
    """Stripe Checkout أو ميسر Invoice (صفحة دفع خارجية)."""
    return isinstance(provider, (StripePaymentProvider, MoyasarPaymentProvider))

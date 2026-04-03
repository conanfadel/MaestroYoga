import os
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

    @staticmethod
    def construct_event(payload: bytes, sig_header: str) -> stripe.Event:
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)


def get_payment_provider() -> BasePaymentProvider:
    provider = os.getenv("PAYMENT_PROVIDER", "mock").lower()
    if provider == "stripe":
        return StripePaymentProvider()
    return MockPaymentProvider()

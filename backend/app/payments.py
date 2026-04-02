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
    ) -> PaymentResult:
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {"name": "Maestro Yoga Session"},
                        "unit_amount": int(round(amount * 100)),
                    },
                    "quantity": 1,
                }
            ],
            metadata=metadata,
        )
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

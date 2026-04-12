"""Select payment provider from PAYMENT_PROVIDER env."""

from __future__ import annotations

import os

from .mock_provider import MockPaymentProvider
from .paymob_provider import PaymobPaymentProvider
from .stripe_provider import StripePaymentProvider
from .types import BasePaymentProvider


def get_payment_provider() -> BasePaymentProvider:
    provider = os.getenv("PAYMENT_PROVIDER", "mock").lower()
    if provider == "stripe":
        return StripePaymentProvider()
    if provider == "paymob":
        return PaymobPaymentProvider()
    return MockPaymentProvider()


def payment_provider_supports_hosted_checkout(provider: BasePaymentProvider) -> bool:
    """Stripe Checkout أو Paymob iframe (صفحة دفع خارجية)."""
    return isinstance(provider, (StripePaymentProvider, PaymobPaymentProvider))

"""Select payment provider from PAYMENT_PROVIDER env."""

from __future__ import annotations

import os

from .moyasar_provider import MoyasarPaymentProvider
from .mock_provider import MockPaymentProvider
from .stripe_provider import StripePaymentProvider
from .types import BasePaymentProvider


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

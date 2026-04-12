"""Select payment provider from PAYMENT_PROVIDER env."""

from __future__ import annotations

import logging
import os

from .mock_provider import MockPaymentProvider
from .paymob_provider import PaymobPaymentProvider
from .stripe_provider import StripePaymentProvider
from .types import BasePaymentProvider

logger = logging.getLogger(__name__)


def get_payment_provider() -> BasePaymentProvider:
    provider = os.getenv("PAYMENT_PROVIDER", "mock").lower()
    if provider == "stripe":
        return StripePaymentProvider()
    if provider == "paymob":
        return PaymobPaymentProvider()
    return MockPaymentProvider()


def resolve_public_payment_provider() -> tuple[BasePaymentProvider | None, str | None]:
    """للواجهة العامة: لا يرمي عند تهيئة stripe/paymob الفاشلة؛ يعيد رسالة للتوجيه بدل 500."""
    mode = os.getenv("PAYMENT_PROVIDER", "mock").strip().lower() or "mock"
    try:
        return get_payment_provider(), None
    except RuntimeError as exc:
        logger.warning("Payment provider init failed (PAYMENT_PROVIDER=%s): %s", mode, exc)
        if mode in ("stripe", "paymob"):
            return None, "payment_provider_config"
        raise


def payment_provider_supports_hosted_checkout(provider: BasePaymentProvider) -> bool:
    """Stripe Checkout أو Paymob iframe (صفحة دفع خارجية)."""
    return isinstance(provider, (StripePaymentProvider, PaymobPaymentProvider))

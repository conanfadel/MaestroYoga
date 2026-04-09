"""Non-production payment provider for tests and local dev."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .types import BasePaymentProvider, PaymentResult


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

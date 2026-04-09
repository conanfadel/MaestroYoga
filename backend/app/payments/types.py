"""Shared payment result type and provider protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


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

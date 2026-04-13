"""Stripe Checkout and webhook verification."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import stripe

from .types import BasePaymentProvider, PaymentResult


class StripePaymentProvider(BasePaymentProvider):
    def __init__(self) -> None:
        secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured")
        stripe.api_key = secret_key

    @staticmethod
    def _stripe_checkout_locale_kw() -> dict[str, Any]:
        locale = os.getenv("STRIPE_CHECKOUT_LOCALE", "auto").strip() or "auto"
        if locale.lower() == "auto":
            return {}
        return {"locale": locale}

    @staticmethod
    def _stripe_product_data(name: str, description: str = "") -> dict[str, Any]:
        product_data: dict[str, Any] = {"name": (name or "Maestro Yoga")[:120]}
        desc = (description or "").strip()
        if desc:
            product_data["description"] = desc[:500]
        return product_data

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
        idempotency_key: str | None = None,
    ) -> PaymentResult:
        """
        Checkout بالبطاقة (SAR). لحساب Stripe مسجّل في السعودية تُقبل بطاقات **مدى**
        ضمن نموذج البطاقة نفسه — راجع توثيق Stripe لمادا.
        """
        product_data = self._stripe_product_data(line_item_name, line_item_description)

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
            "payment_intent_data": {"metadata": dict(metadata)},
        }
        create_kwargs.update(self._stripe_checkout_locale_kw())

        idem = (idempotency_key or "").strip() or None
        if idem:
            session = stripe.checkout.Session.create(**create_kwargs, idempotency_key=idem[:255])
        else:
            session = stripe.checkout.Session.create(**create_kwargs)
        return PaymentResult(provider_ref=session.id, status="pending", checkout_url=session.url)

    def create_checkout_session_multi_line(
        self,
        currency: str,
        line_specs: list[tuple[float, str, str]],
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
        *,
        idempotency_key: str | None = None,
    ) -> PaymentResult:
        if not line_specs:
            raise ValueError("line_specs required")
        line_items: list[dict[str, Any]] = []
        for amount, name, description in line_specs:
            product_data = self._stripe_product_data(name, description)
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
            "payment_intent_data": {"metadata": dict(metadata)},
        }
        create_kwargs.update(self._stripe_checkout_locale_kw())
        idem = (idempotency_key or "").strip() or None
        if idem:
            session = stripe.checkout.Session.create(**create_kwargs, idempotency_key=idem[:255])
        else:
            session = stripe.checkout.Session.create(**create_kwargs)
        return PaymentResult(provider_ref=session.id, status="pending", checkout_url=session.url)

    @staticmethod
    def construct_event(payload: bytes, sig_header: str) -> stripe.Event:
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

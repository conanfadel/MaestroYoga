"""Paymob Accept API: auth token, order, payment key, hosted iframe checkout."""

from __future__ import annotations

import hashlib
import logging
import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .types import BasePaymentProvider, PaymentResult

logger = logging.getLogger(__name__)

_HMAC_FIELD_PATHS: list[tuple[str, ...]] = [
    ("obj", "amount_cents"),
    ("obj", "created_at"),
    ("obj", "currency"),
    ("obj", "error_occured"),
    ("obj", "has_parent_transaction"),
    ("obj", "id"),
    ("obj", "integration_id"),
    ("obj", "is_3d_secure"),
    ("obj", "is_auth"),
    ("obj", "is_capture"),
    ("obj", "is_refunded"),
    ("obj", "is_standalone_payment"),
    ("obj", "is_voided"),
    ("obj", "order", "id"),
    ("obj", "owner"),
    ("obj", "pending"),
    ("obj", "source_data", "pan"),
    ("obj", "source_data", "sub_type"),
    ("obj", "source_data", "type"),
    ("obj", "success"),
]


def _deep_get(data: object, keys: tuple[str, ...]) -> str:
    cur: object = data
    for key in keys:
        if not isinstance(cur, dict):
            return ""
        v = cur.get(key)
        if v is None:
            return ""
        cur = v
    if isinstance(cur, bool):
        return "true" if cur else "false"
    return str(cur)


def verify_paymob_processed_hmac(payload: dict[str, Any], hmac_received: str, secret: str) -> bool:
    """HMAC-SHA512 لمعالجة المعاملة (POST) كما في توثيق Paymob / paymobx."""
    msg = "".join(_deep_get(payload, path) for path in _HMAC_FIELD_PATHS)
    gen = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha512).hexdigest()
    return hmac.compare_digest(gen, (hmac_received or "").strip())


def encode_paymob_merchant_order_ref(metadata: dict[str, Any]) -> str:
    """يُخزَّن في merchant_order_id ويُعاد من webhook لاستخراج metadata."""
    md = {k: str(v).strip() for k, v in metadata.items() if v is not None and str(v).strip()}
    pids_raw = md.get("payment_ids", "")
    if pids_raw:
        parts = [p.strip() for p in str(pids_raw).split(",") if p.strip().isdigit()]
        if len(parts) > 1:
            return "mC" + ".".join(parts)
        if len(parts) == 1:
            return f"mP{parts[0]}"
    if md.get("subscription_id") and md.get("payment_id"):
        return f"mS{md['subscription_id']}P{md['payment_id']}"
    if md.get("payment_id"):
        return f"mP{md['payment_id']}"
    return "mP0"


def parse_paymob_merchant_order_ref(merchant_order_id: str | None) -> dict[str, str]:
    if not merchant_order_id:
        return {}
    s = str(merchant_order_id).strip()
    if not s:
        return {}
    if s.startswith("mC") and len(s) > 2:
        return {"payment_ids": s[2:].replace(".", ",")}
    m = re.match(r"^mS(\d+)P(\d+)$", s)
    if m:
        return {"subscription_id": m.group(1), "payment_id": m.group(2)}
    m = re.match(r"^mP(\d+)$", s)
    if m:
        return {"payment_id": m.group(1)}
    return {}


def metadata_from_paymob_obj(obj: dict[str, Any]) -> dict[str, str]:
    order = obj.get("order")
    merchant_order_id: str | None = None
    if isinstance(order, dict):
        mid = order.get("merchant_order_id")
        if mid is not None:
            merchant_order_id = str(mid)
    meta = parse_paymob_merchant_order_ref(merchant_order_id)
    return {k: str(v) for k, v in meta.items()}


class PaymobPaymentProvider(BasePaymentProvider):
    """Paymob Accept: تسجيل طلب + payment key + إعادة توجيه لصفحة الدفع المستضافة."""

    def __init__(self) -> None:
        # POST /api/auth/tokens يتوقّع الحقل JSON اسمه api_key؛ قيمته في لوحة Paymob غالباً «API Key» أو «Secret Key».
        self._api_key = os.getenv("PAYMOB_API_KEY", "").strip() or os.getenv("PAYMOB_SECRET_KEY", "").strip()
        if not self._api_key:
            raise RuntimeError(
                "Paymob auth not configured: set PAYMOB_API_KEY (dashboard API Key) "
                "or PAYMOB_SECRET_KEY (dashboard Secret Key) for /api/auth/tokens."
            )
        iid = (
            os.getenv("PAYMOB_INTEGRATION_ID", "").strip()
            or os.getenv("PAYMOB_CARD_INTEGRATION_ID", "").strip()
        )
        if not iid.isdigit():
            raise RuntimeError(
                "PAYMOB_INTEGRATION_ID (or PAYMOB_CARD_INTEGRATION_ID) must be a numeric "
                "Online Card / payment integration id from Paymob Dashboard → Developers → Payment Integrations."
            )
        self._integration_id = int(iid)
        fid = os.getenv("PAYMOB_IFRAME_ID", "").strip()
        mirror = os.getenv("PAYMOB_MIRROR_IFRAME_TO_INTEGRATION", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not fid.isdigit():
            if mirror:
                fid = iid
                logger.warning(
                    "PAYMOB_IFRAME_ID unset: using PAYMOB_INTEGRATION_ID for iframe URL "
                    "(PAYMOB_MIRROR_IFRAME_TO_INTEGRATION=1). If checkout fails, obtain a separate Iframe ID "
                    "from Paymob Dashboard → Developers → iframes."
                )
            else:
                raise RuntimeError(
                    "PAYMOB_IFRAME_ID must be a numeric iframe id (Paymob Dashboard → Developers → iframes). "
                    "If your account only shows one id for card checkout, set PAYMOB_INTEGRATION_ID to that "
                    "number and add PAYMOB_MIRROR_IFRAME_TO_INTEGRATION=1 to reuse it for the iframe URL."
                )
        self._iframe_id = int(fid)
        self._api_base = os.getenv("PAYMOB_API_BASE", "https://accept.paymob.com").strip().rstrip("/")
        self._auth_token: str | None = None

    def _billing_data(self) -> dict[str, str]:
        def g(name: str, default: str) -> str:
            return os.getenv(name, default).strip() or default

        return {
            "apartment": g("PAYMOB_BILLING_APARTMENT", "NA"),
            "email": g("PAYMOB_BILLING_EMAIL", "checkout@example.invalid"),
            "floor": g("PAYMOB_BILLING_FLOOR", "NA"),
            "first_name": g("PAYMOB_BILLING_FIRST_NAME", "Customer"),
            "street": g("PAYMOB_BILLING_STREET", "NA"),
            "building": g("PAYMOB_BILLING_BUILDING", "NA"),
            "phone_number": g("PAYMOB_BILLING_PHONE", "+966500000000"),
            "shipping_method": g("PAYMOB_BILLING_SHIPPING_METHOD", "NA"),
            "postal_code": g("PAYMOB_BILLING_POSTAL_CODE", "NA"),
            "city": g("PAYMOB_BILLING_CITY", "NA"),
            "country": g("PAYMOB_BILLING_COUNTRY", "SA"),
            "last_name": g("PAYMOB_BILLING_LAST_NAME", "NA"),
            "state": g("PAYMOB_BILLING_STATE", "NA"),
        }

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._api_base}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"paymob_http_{exc.code}:{err_body[:500]}") from exc
        return json.loads(raw) if raw else {}

    def _authenticate(self) -> str:
        if self._auth_token:
            return self._auth_token
        out = self._post_json("/api/auth/tokens", {"api_key": self._api_key})
        token = out.get("token")
        if not token or not isinstance(token, str):
            raise RuntimeError(f"paymob_auth_failed:{json.dumps(out)[:200]}")
        self._auth_token = token
        return token

    def _amount_to_cents(self, amount: float, currency: str) -> int:
        _ = currency
        cents = int(round(float(amount) * 100))
        if cents < 1:
            raise RuntimeError("paymob_min_amount: amount must be at least 0.01 in the given currency.")
        return cents

    def _create_checkout(
        self,
        *,
        amount_cents: int,
        currency: str,
        metadata: dict[str, Any],
        success_url: str,
        cancel_url: str,
        description: str,
    ) -> PaymentResult:
        _ = cancel_url
        _ = description
        auth = self._authenticate()
        cur = currency.upper().strip() or "SAR"
        merchant_ref = encode_paymob_merchant_order_ref(metadata)
        order_body: dict[str, Any] = {
            "auth_token": auth,
            "delivery_needed": False,
            "amount_cents": amount_cents,
            "currency": cur,
            "items": [],
            "merchant_order_id": merchant_ref,
        }
        order = self._post_json("/api/ecommerce/orders", order_body)
        order_id = order.get("id")
        if order_id is None:
            raise RuntimeError(f"paymob_invalid_order:{json.dumps(order)[:300]}")
        oid = int(order_id) if not isinstance(order_id, int) else order_id

        key_body: dict[str, Any] = {
            "auth_token": auth,
            "amount_cents": amount_cents,
            "expiration": 3600,
            "order_id": oid,
            "billing_data": self._billing_data(),
            "currency": cur,
            "integration_id": self._integration_id,
            "lock_order_when_paid": False,
        }
        skip_redir = os.getenv("PAYMOB_SKIP_REDIRECTION_URL", "").strip().lower() in ("1", "true", "yes")
        if success_url.strip() and not skip_redir:
            key_body["redirection_url"] = success_url.strip()[:500]

        keys = self._post_json("/api/acceptance/payment_keys", key_body)
        pay_token = keys.get("token")
        if not pay_token or not isinstance(pay_token, str):
            raise RuntimeError(f"paymob_invalid_payment_key:{json.dumps(keys)[:300]}")

        tok_q = urllib.parse.quote(pay_token, safe="")
        checkout_url = f"{self._api_base}/api/acceptance/iframes/{self._iframe_id}?payment_token={tok_q}"
        return PaymentResult(provider_ref=str(oid), status="pending", checkout_url=checkout_url)

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
        cents = self._amount_to_cents(amount, currency)
        desc = f"{line_item_name} — {line_item_description}".strip()[:500] or line_item_name
        return self._create_checkout(
            amount_cents=cents,
            currency=currency,
            metadata=metadata,
            success_url=success_url,
            cancel_url=cancel_url,
            description=desc,
        )

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
        total = sum(float(a) for a, _, _ in line_specs)
        cents = self._amount_to_cents(total, currency)
        parts = [f"{name}: {float(amt):.2f}" for amt, name, _ in line_specs]
        desc = " | ".join(parts)[:500]
        return self._create_checkout(
            amount_cents=cents,
            currency=currency,
            metadata=metadata,
            success_url=success_url,
            cancel_url=cancel_url,
            description=desc,
        )

    def charge(self, amount: float, currency: str, metadata: dict) -> PaymentResult:
        _ = (amount, currency, metadata)
        raise NotImplementedError("Paymob uses hosted iframe checkout only")

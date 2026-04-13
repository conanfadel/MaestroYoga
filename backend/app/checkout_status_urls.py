"""روابط صفحة حالة الدفع العامة (`/checkout-status`) مع توقيع يمنع تخمين معرفات المدفوعات."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from urllib.parse import urlencode


def checkout_status_signing_secret() -> str:
    return (
        os.getenv("PUBLIC_JWT_SECRET", "").strip()
        or os.getenv("JWT_SECRET", "").strip()
        or "change-this-in-production"
    )


def checkout_status_signature(center_id: int, payment_ids: list[int]) -> str:
    ids = sorted({int(p) for p in payment_ids if int(p) > 0})
    msg = f"{int(center_id)}|{','.join(str(i) for i in ids)}"
    return hmac.new(
        checkout_status_signing_secret().encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_checkout_status_signature(center_id: int, payment_ids: list[int], sig: str) -> bool:
    if not sig or not isinstance(sig, str):
        return False
    expected = checkout_status_signature(center_id, payment_ids)
    return hmac.compare_digest(expected.strip().lower(), sig.strip().lower())


def parse_payment_ids_param(
    *,
    payment_id: int | None,
    payment_ids_raw: str | None,
) -> list[int] | None:
    if payment_id is not None and payment_id > 0 and not (payment_ids_raw or "").strip():
        return [int(payment_id)]
    raw = (payment_ids_raw or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out: list[int] = []
    for p in parts:
        if not re.fullmatch(r"\d+", p):
            return None
        out.append(int(p))
    return sorted(set(out)) if out else None


def build_checkout_status_url(
    base_url: str,
    center_id: int,
    payment_ids: list[int],
    *,
    result: str | None = None,
    flow: str | None = None,
) -> str:
    """رابط نجاح/إلغاء موحّد لـ Paymob وStripe (يُقرَأ من قاعدة البيانات في الصفحة)."""
    base = base_url.rstrip("/")
    ids = sorted({int(p) for p in payment_ids if int(p) > 0})
    if not ids:
        raise ValueError("payment_ids required")
    sig = checkout_status_signature(center_id, ids)
    q: list[tuple[str, str]] = [
        ("center_id", str(int(center_id))),
        ("sig", sig),
    ]
    if len(ids) == 1:
        q.append(("payment_id", str(ids[0])))
    else:
        q.append(("payment_ids", ",".join(str(i) for i in ids)))
    if result:
        q.append(("result", str(result)))
    if flow:
        q.append(("flow", str(flow)))
    return f"{base}/checkout-status?{urlencode(q)}"

from urllib.parse import urlencode

from fastapi import Request

from . import models
from .security import create_public_account_delete_token
from .web_shared import _public_base, _sanitize_next_url, PUBLIC_INDEX_DEFAULT_PATH


def public_account_phone_prefill(user: models.PublicUser) -> tuple[str, str]:
    """(country_code, local_digits) for account form; default +966 if unknown."""
    raw = (user.phone or "").strip()
    if not raw:
        return "+966", ""
    for prefix in ("+966", "+971", "+965", "+973", "+974", "+968", "+20"):
        if raw.startswith(prefix):
            return prefix, raw[len(prefix) :].lstrip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return "+966", digits


def build_account_delete_confirm_url(
    request: Request, user: models.PublicUser, next_url: str = PUBLIC_INDEX_DEFAULT_PATH
) -> str:
    token = create_public_account_delete_token(user.id, user.email)
    safe_next = _sanitize_next_url(next_url)
    query = urlencode({"token": token, "next": safe_next})
    return f"{_public_base(request)}/public/account/delete/confirm?{query}"

import ipaddress
import os

from fastapi import Request


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _trusted_proxy_ips() -> set[str]:
    raw = os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    if not _is_truthy(os.getenv("TRUST_PROXY_HEADERS", "0")):
        return direct_ip

    if direct_ip not in _trusted_proxy_ips():
        return direct_ip

    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    if x_forwarded_for:
        first = x_forwarded_for.split(",")[0].strip()
        if _valid_ip(first):
            return first

    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip and _valid_ip(x_real_ip):
        return x_real_ip

    return direct_ip

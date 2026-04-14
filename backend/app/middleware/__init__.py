"""
وسائط طبقة التطبيق: معرّف الطلب، وضع الصيانة، وتهيئة CORS للعملاء (متصفح / WebView / أدوات).
"""

from __future__ import annotations

from .api_client_headers import ApiClientHeadersMiddleware
from .cors import attach_cors
from .idle_timeout import IdleTimeoutMiddleware
from .maintenance import MaintenanceMiddleware, maintenance_enabled
from .rate_limit import (
    RateLimitMiddleware,
    clear_rate_limit_buckets_for_tests,
    rate_limit_middleware_enabled,
)
from .request_id import RequestIDMiddleware

__all__ = [
    "ApiClientHeadersMiddleware",
    "IdleTimeoutMiddleware",
    "MaintenanceMiddleware",
    "RateLimitMiddleware",
    "RequestIDMiddleware",
    "attach_cors",
    "clear_rate_limit_buckets_for_tests",
    "maintenance_enabled",
    "rate_limit_middleware_enabled",
]

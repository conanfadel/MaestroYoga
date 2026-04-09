"""Environment-driven constants for the JSON REST API."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

SEED_DEMO_KEY = os.getenv("SEED_DEMO_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
STRIPE_CHECKOUT_ALLOWED_ORIGINS = [
    x.strip().rstrip("/") for x in os.getenv("STRIPE_CHECKOUT_ALLOWED_ORIGINS", "").split(",") if x.strip()
]

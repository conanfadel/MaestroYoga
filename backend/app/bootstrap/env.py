"""Environment gates for automatic demo seeding."""

import os


def should_auto_seed_demo_data() -> bool:
    """Gate demo seed to development-like environments unless explicitly enabled."""
    allow = os.getenv("ALLOW_DEMO_SEED")
    if allow is not None:
        return allow.strip().lower() in {"1", "true", "yes", "on"}
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    return app_env in {"development", "dev", "local", "test", "testing"}

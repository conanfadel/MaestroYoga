"""Demo seed data and environment gates (same public API as former bootstrap.py)."""

from .constants import DEMO_CENTER_NAME, DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD
from .demo_data import ensure_demo_data
from .demo_news import DEMO_NEWS_POSTS, ensure_demo_news_posts
from .env import should_auto_seed_demo_data

__all__ = [
    "DEMO_CENTER_NAME",
    "DEMO_NEWS_POSTS",
    "DEMO_OWNER_EMAIL",
    "DEMO_OWNER_PASSWORD",
    "ensure_demo_data",
    "ensure_demo_news_posts",
    "should_auto_seed_demo_data",
]

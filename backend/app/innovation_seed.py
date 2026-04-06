"""بذور افتراضية لميزات اختيارية (أعلام)."""

from __future__ import annotations

import logging

from . import models
from .database import SessionLocal

logger = logging.getLogger(__name__)


def seed_default_feature_flags() -> None:
    db = SessionLocal()
    try:
        defaults = [
            ("feature_waitlist", True),
            ("feature_ratings", True),
            ("feature_referrals", True),
        ]
        for key, en in defaults:
            exists = (
                db.query(models.FeatureFlag)
                .filter(models.FeatureFlag.flag_key == key, models.FeatureFlag.center_id.is_(None))
                .first()
            )
            if exists:
                continue
            db.add(models.FeatureFlag(center_id=None, flag_key=key, enabled=en))
        db.commit()
    except Exception as exc:
        logger.warning("seed_default_feature_flags: %s", exc)
        db.rollback()
    finally:
        db.close()

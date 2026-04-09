from sqlalchemy.orm import Session

from . import models
from .loyalty import count_confirmed_sessions_for_public_user, loyalty_context_for_count


def build_public_loyalty_context(
    db: Session,
    center_id: int,
    public_user: models.PublicUser | None,
    *,
    center: models.Center | None = None,
) -> dict:
    if not public_user:
        return {}
    return loyalty_context_for_count(
        count_confirmed_sessions_for_public_user(db, center_id, public_user),
        center=center,
    )

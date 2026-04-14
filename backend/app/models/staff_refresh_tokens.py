"""Persisted staff refresh-token sessions (rotation + revocation)."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from ..database import Base
from ..time_utils import utcnow_naive


class StaffRefreshToken(Base):
    __tablename__ = "staff_refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)

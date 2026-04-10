from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..database import Base
from ..time_utils import utcnow_naive


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True, index=True)
    ip = Column(String, nullable=True, index=True)
    user_agent = Column(String, nullable=True)
    path = Column(String, nullable=True)
    details_json = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive, index=True)


class BlockedIP(Base):
    __tablename__ = "blocked_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False, unique=True, index=True)
    reason = Column(String, nullable=True)
    blocked_until = Column(DateTime, nullable=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive, index=True)

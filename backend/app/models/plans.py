from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    plan_type = Column(String, nullable=False)  # monthly | yearly
    price = Column(Float, nullable=False)
    session_limit = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)

    center = relationship("Center", back_populates="plans")
    subscriptions = relationship("ClientSubscription", back_populates="plan")


class FAQItem(Base):
    __tablename__ = "faq_items"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    center = relationship("Center", back_populates="faqs")

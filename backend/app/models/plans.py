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
    list_price = Column(Float, nullable=True)
    discount_mode = Column(String(16), nullable=False, default="none")
    discount_percent = Column(Float, nullable=True)
    discount_schedule_type = Column(String(24), nullable=False, default="always")
    discount_valid_from = Column(DateTime, nullable=True)
    discount_valid_until = Column(DateTime, nullable=True)
    discount_hour_start = Column(Integer, nullable=True)
    discount_hour_end = Column(Integer, nullable=True)
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

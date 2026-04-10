from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)

    center = relationship("Center", back_populates="clients")
    subscriptions = relationship("ClientSubscription", back_populates="client")
    bookings = relationship("Booking", back_populates="client")
    payments = relationship("Payment", back_populates="client")


class ClientSubscription(Base):
    __tablename__ = "client_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String, default="active", index=True)

    client = relationship("Client", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")

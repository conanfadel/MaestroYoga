from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base
from .time_utils import utcnow_naive


class Center(Base):
    __tablename__ = "centers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    city = Column(String, nullable=True)

    clients = relationship("Client", back_populates="center")
    plans = relationship("SubscriptionPlan", back_populates="center")
    rooms = relationship("Room", back_populates="center")
    sessions = relationship("YogaSession", back_populates="center")
    users = relationship("User", back_populates="center")
    faqs = relationship("FAQItem", back_populates="center")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="center_staff")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow_naive)

    center = relationship("Center", back_populates="users")


class PublicUser(Base):
    __tablename__ = "public_users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=True, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    email_verified = Column(Boolean, default=False)
    verification_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)

    center = relationship("Center", back_populates="clients")
    subscriptions = relationship("ClientSubscription", back_populates="client")
    bookings = relationship("Booking", back_populates="client")
    payments = relationship("Payment", back_populates="client")


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False)
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


class ClientSubscription(Base):
    __tablename__ = "client_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String, default="active")

    client = relationship("Client", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False, default=10)

    center = relationship("Center", back_populates="rooms")
    sessions = relationship("YogaSession", back_populates="room")


class YogaSession(Base):
    __tablename__ = "yoga_sessions"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    title = Column(String, nullable=False)
    trainer_name = Column(String, nullable=False)
    level = Column(String, nullable=False)  # beginner/intermediate/advanced
    starts_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)
    price_drop_in = Column(Float, nullable=False, default=0.0)

    center = relationship("Center", back_populates="sessions")
    room = relationship("Room", back_populates="sessions")
    bookings = relationship("Booking", back_populates="session")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("yoga_sessions.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    # booked legacy | confirmed paid or staff | pending_payment awaiting payment | cancelled
    status = Column(String, default="booked")
    booked_at = Column(DateTime, default=utcnow_naive)

    session = relationship("YogaSession", back_populates="bookings")
    client = relationship("Client", back_populates="bookings")
    payments = relationship("Payment", back_populates="booking")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="SAR")
    payment_method = Column(String, default="in_app_mock")
    provider_ref = Column(String, nullable=True)
    status = Column(String, default="paid")
    paid_at = Column(DateTime, default=utcnow_naive)

    client = relationship("Client", back_populates="payments")
    booking = relationship("Booking", back_populates="payments")


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

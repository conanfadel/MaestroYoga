from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base
from ..time_utils import utcnow_naive


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("yoga_sessions.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    # booked legacy | confirmed paid or staff | pending_payment awaiting payment | cancelled
    status = Column(String, default="booked", index=True)
    booked_at = Column(DateTime, default=utcnow_naive, index=True)
    # حضور: NULL لم يُسجَّل بعد، True حضر، False تغيّب (للجلسات الماضية)
    checked_in = Column(Boolean, nullable=True)

    session = relationship("YogaSession", back_populates="bookings")
    client = relationship("Client", back_populates="bookings")
    payments = relationship("Payment", back_populates="booking")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="SAR")
    payment_method = Column(String, default="in_app_mock")
    provider_ref = Column(String, nullable=True)
    status = Column(String, default="paid", index=True)
    paid_at = Column(DateTime, default=utcnow_naive, index=True)
    created_at = Column(DateTime, default=utcnow_naive, index=True)

    client = relationship("Client", back_populates="payments")
    booking = relationship("Booking", back_populates="payments")

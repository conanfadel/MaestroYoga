from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False, default=10)

    center = relationship("Center", back_populates="rooms")
    sessions = relationship("YogaSession", back_populates="room")


class YogaSession(Base):
    __tablename__ = "yoga_sessions"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=False, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    trainer_name = Column(String, nullable=False)
    level = Column(String, nullable=False)  # beginner/intermediate/advanced
    starts_at = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False, default=60)
    price_drop_in = Column(Float, nullable=False, default=0.0)
    # list_price = السعر الأساسي (يُعرض مشطوبًا عند وجود خصم). price_drop_in = المبلغ المُحتسب للدفع.
    list_price = Column(Float, nullable=True)
    discount_mode = Column(String(16), nullable=False, default="none")  # none | percent | fixed
    discount_percent = Column(Float, nullable=True)
    # متى يُطبَّق سعر الخصم: دائماً | بين تاريخين | نافذة يومية بتوقيت السعودية
    discount_schedule_type = Column(String(24), nullable=False, default="always")
    discount_valid_from = Column(DateTime, nullable=True)
    discount_valid_until = Column(DateTime, nullable=True)
    discount_hour_start = Column(Integer, nullable=True)
    discount_hour_end = Column(Integer, nullable=True)

    center = relationship("Center", back_populates="sessions")
    room = relationship("Room", back_populates="sessions")
    bookings = relationship("Booking", back_populates="session")

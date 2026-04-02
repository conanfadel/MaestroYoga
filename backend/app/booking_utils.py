from sqlalchemy.orm import Session

from . import models

# Counts toward room capacity (legacy "booked" included).
ACTIVE_BOOKING_STATUSES = ("booked", "confirmed", "pending_payment")


def count_active_bookings(db: Session, session_id: int) -> int:
    return (
        db.query(models.Booking)
        .filter(
            models.Booking.session_id == session_id,
            models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .count()
    )


def spots_available(db: Session, session: models.YogaSession) -> int:
    room = db.get(models.Room, session.room_id)
    if not room:
        return 0
    return max(0, room.capacity - count_active_bookings(db, session.id))

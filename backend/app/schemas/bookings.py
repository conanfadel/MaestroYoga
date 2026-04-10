from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BookingCreate(BaseModel):
    session_id: int
    client_id: int


class BookingOut(BaseModel):
    id: int
    center_id: int
    session_id: int
    client_id: int
    status: str
    booked_at: datetime

    model_config = ConfigDict(from_attributes=True)

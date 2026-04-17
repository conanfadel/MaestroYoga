from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RoomCreate(BaseModel):
    name: str
    capacity: int = 10


class RoomOut(BaseModel):
    id: int
    center_id: int
    name: str
    capacity: int

    model_config = ConfigDict(from_attributes=True)


class YogaSessionCreate(BaseModel):
    room_id: int
    title: str
    trainer_name: str
    level: str
    starts_at: datetime
    duration_minutes: int = 60
    price_drop_in: float = 0.0


class YogaSessionOut(YogaSessionCreate):
    id: int
    center_id: int
    list_price: Optional[float] = None
    discount_mode: str = "none"
    discount_percent: Optional[float] = None
    discount_schedule_type: str = "always"
    discount_valid_from: Optional[datetime] = None
    discount_valid_until: Optional[datetime] = None
    discount_hour_start: Optional[int] = None
    discount_hour_end: Optional[int] = None
    discount_duration_hours: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

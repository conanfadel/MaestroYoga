from datetime import datetime

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

    model_config = ConfigDict(from_attributes=True)

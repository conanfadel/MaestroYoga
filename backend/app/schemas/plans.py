from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionPlanCreate(BaseModel):
    name: str
    plan_type: str = Field(pattern="^(weekly|monthly|yearly)$")
    price: float
    session_limit: Optional[int] = None


class SubscriptionPlanOut(BaseModel):
    id: int
    center_id: int
    name: str
    plan_type: str
    price: float
    list_price: Optional[float] = None
    discount_mode: str = "none"
    discount_percent: Optional[float] = None
    discount_schedule_type: str = "always"
    discount_valid_from: Optional[datetime] = None
    discount_valid_until: Optional[datetime] = None
    discount_hour_start: Optional[int] = None
    discount_hour_end: Optional[int] = None
    session_limit: Optional[int] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

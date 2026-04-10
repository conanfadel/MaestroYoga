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
    session_limit: Optional[int] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

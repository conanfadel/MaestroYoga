from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ClientCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None


class ClientOut(BaseModel):
    id: int
    center_id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    subscription_number: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

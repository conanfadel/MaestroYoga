from typing import Optional

from pydantic import BaseModel, ConfigDict


class CenterCreate(BaseModel):
    name: str
    city: Optional[str] = None


class CenterOut(CenterCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PaymentCreate(BaseModel):
    client_id: int
    amount: float
    currency: str = "SAR"
    payment_method: str = "in_app_mock"


class PaymentCheckoutCreate(BaseModel):
    client_id: int
    amount: float
    currency: str = "sar"
    success_url: str
    cancel_url: str


class PaymentCheckoutOut(BaseModel):
    payment_id: int
    checkout_url: str
    provider_ref: str
    status: str


class PaymentOut(BaseModel):
    id: int
    center_id: int
    client_id: int
    booking_id: Optional[int] = None
    amount: float
    currency: str
    payment_method: str
    provider_ref: Optional[str] = None
    status: str
    paid_at: datetime
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

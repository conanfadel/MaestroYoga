from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .role_definitions import ASSIGNABLE_BY_CENTER_OWNER


class UserRegister(BaseModel):
    full_name: str
    email: str
    password: str = Field(min_length=8)
    center_name: str
    city: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserCreateByOwner(BaseModel):
    full_name: str
    email: str
    password: str = Field(min_length=8)
    role: str

    @field_validator("role")
    @classmethod
    def _role_assignable(cls, v: str) -> str:
        if v not in ASSIGNABLE_BY_CENTER_OWNER:
            raise ValueError("unsupported staff role")
        return v


class UserOut(BaseModel):
    id: int
    center_id: Optional[int] = None
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DashboardSummaryOut(BaseModel):
    center_id: int
    clients_count: int
    sessions_count: int
    bookings_count: int
    active_plans_count: int
    revenue_total: float
    revenue_today: float
    pending_payments_count: int


class CenterCreate(BaseModel):
    name: str
    city: Optional[str] = None


class CenterOut(CenterCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)

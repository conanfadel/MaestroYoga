from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .role_definitions import ASSIGNABLE_BY_CENTER_OWNER, CUSTOM_STAFF_ALLOWED_PERMISSIONS


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
    custom_role_label: Optional[str] = None
    permission_ids: Optional[list[str]] = None

    @field_validator("role")
    @classmethod
    def _role_assignable(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in ASSIGNABLE_BY_CENTER_OWNER:
            raise ValueError("unsupported staff role")
        return v

    @model_validator(mode="after")
    def _custom_staff(self):
        if self.role != "custom_staff":
            self.custom_role_label = None
            self.permission_ids = None
            return self
        label = (self.custom_role_label or "").strip()
        if len(label) < 2:
            raise ValueError("custom_role_label_required")
        raw = self.permission_ids or []
        cleaned = sorted({x for x in raw if isinstance(x, str) and x in CUSTOM_STAFF_ALLOWED_PERMISSIONS})
        if not cleaned:
            raise ValueError("custom_permissions_required")
        self.custom_role_label = label[:120]
        self.permission_ids = cleaned
        return self


class UserOut(BaseModel):
    id: int
    center_id: Optional[int] = None
    full_name: str
    email: str
    role: str
    custom_role_label: Optional[str] = None
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
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

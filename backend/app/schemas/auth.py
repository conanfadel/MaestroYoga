from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..role_definitions import ASSIGNABLE_BY_CENTER_OWNER, CUSTOM_STAFF_ALLOWED_PERMISSIONS


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
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: UserOut


class RefreshTokenIn(BaseModel):
    refresh_token: str = Field(min_length=20)

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

MIN_PASSWORD_LENGTH = 8


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str = ""

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        return v


class UserUpdate(BaseModel):
    password: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def _validate_password_update(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class IntrospectIn(BaseModel):
    token: str


class IntrospectOut(BaseModel):
    active: bool
    username: Optional[str] = None
    user_id: Optional[int] = None
    full_name: str = ""

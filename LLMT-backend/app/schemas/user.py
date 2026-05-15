"""User schemas for system management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserRoleOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class UserListOut(BaseModel):
    id: int
    username: str
    real_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    status: str
    is_superuser: bool
    roles: list[UserRoleOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    username: str
    real_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    status: str
    is_superuser: bool
    roles: list[UserRoleOut] = []
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    real_name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    real_name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[str] = Field(default=None, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    password: Optional[str] = Field(default=None, min_length=6, max_length=64)


class UserStatusUpdate(BaseModel):
    status: str = Field(..., description="active | locked | disabled")


class UserRoleUpdate(BaseModel):
    role_ids: list[int]

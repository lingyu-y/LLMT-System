"""Role schemas for system management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RoleOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    role_type: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleListOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    role_type: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=256)
    role_type: Optional[str] = Field(default=None, max_length=32)
    permission_ids: list[int] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=256)
    role_type: Optional[str] = Field(default=None, max_length=32)
    permission_ids: Optional[list[int]] = None


class RoleStatusUpdate(BaseModel):
    status: str = Field(..., description="active | disabled")

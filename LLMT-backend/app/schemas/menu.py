"""Menu and Permission schemas for system management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class MenuTreeOut(BaseModel):
    id: int
    key: str
    name: str
    path: str
    icon: str
    parent_id: Optional[int]
    sort_order: int
    children: list["MenuTreeOut"] = []

    model_config = {"from_attributes": True}

    @field_validator("children", mode="before")
    @classmethod
    def _default_children(cls, v):
        return v if v is not None else []


class PermissionListOut(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: Optional[str]

    model_config = {"from_attributes": True}


class RoleMenuUpdate(BaseModel):
    menu_ids: list[int]

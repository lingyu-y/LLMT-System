"""Menu and Permission schemas for system management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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


class PermissionListOut(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: Optional[str]

    model_config = {"from_attributes": True}


class RoleMenuUpdate(BaseModel):
    menu_ids: list[int]

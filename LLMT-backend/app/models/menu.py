"""Menu model."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Menu(IdMixin, TimestampMixin, Base):
    """Sidebar menu tree node."""

    __tablename__ = "menus"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(256), default="")
    icon: Mapped[str] = mapped_column(String(64), default="")
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("menus.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    children: Mapped[list["Menu"]] = relationship(
        "Menu", back_populates="parent", lazy="selectin"
    )
    parent: Mapped[Optional["Menu"]] = relationship(
        "Menu", back_populates="children", remote_side="Menu.id", lazy="selectin"
    )
    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="role_menus", back_populates="menus"
    )

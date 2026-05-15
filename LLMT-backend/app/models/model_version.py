"""Model version model."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class ModelVersion(IdMixin, TimestampMixin, Base):
    """Versioned model artifact metadata."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "model_code",
            "version",
            name="uq_model_versions_model_code_version",
        ),
    )

    model_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    model_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    tag: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    framework: Mapped[str | None] = mapped_column(String(32))
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    hyperparams_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    dataset_version: Mapped[str | None] = mapped_column(String(32))
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_tasks.id", ondelete="SET NULL"),
        index=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    training_task: Mapped["TrainingTask | None"] = relationship(
        "TrainingTask",
        back_populates="model_versions",
    )
    created_by: Mapped["User | None"] = relationship(
        "User",
        back_populates="model_versions",
    )

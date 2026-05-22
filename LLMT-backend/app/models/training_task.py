"""Training task model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class TrainingTask(IdMixin, TimestampMixin, Base):
    """Offline model training task."""

    __tablename__ = "training_tasks"

    task_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    task_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    framework: Mapped[str | None] = mapped_column(String(32))
    parallel_strategy: Mapped[str | None] = mapped_column(String(64))
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    current_epoch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_epoch: Mapped[int | None] = mapped_column(Integer)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkpoint_path: Mapped[str | None] = mapped_column(String(512))
    error_message: Mapped[str | None] = mapped_column(Text)
    # celery_task_id: Mapped[str | None] = mapped_column(  # TODO: run migration
    #     String(128),
    #     index=True,
    #     nullable=True,
    #     comment="Celery AsyncResult.id returned by delay()/apply_async()",
    # )

    creator: Mapped["User"] = relationship(
        "User",
        back_populates="training_tasks",
    )
    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="training_tasks",
    )
    model_versions: Mapped[list["ModelVersion"]] = relationship(
        "ModelVersion",
        back_populates="training_task",
    )

"""Dataset model."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Dataset(IdMixin, TimestampMixin, Base):
    """Dataset metadata stored for training and preprocessing."""

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(
        String(32),
        default="v1.0.0",
        nullable=False,
    )
    source: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    quality_status: Mapped[str] = mapped_column(
        String(32),
        default="unchecked",
        nullable=False,
    )
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )
    lineage_status: Mapped[str] = mapped_column(
        String(32),
        default="none",
        nullable=False,
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    owner: Mapped["User"] = relationship("User", back_populates="datasets")
    training_tasks: Mapped[list["TrainingTask"]] = relationship(
        "TrainingTask",
        back_populates="dataset",
    )

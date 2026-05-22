"""Federated learning task model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class FederatedTask(IdMixin, TimestampMixin, Base):
    """Federated learning training task."""

    __tablename__ = "federated_tasks"

    task_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    task_code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)

    # Status: created | initializing | running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)

    # Model config
    model_type: Mapped[str] = mapped_column(String(32), default="gpt2")
    model_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Federated config
    num_rounds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    aggregation_strategy: Mapped[str] = mapped_column(String(32), default="weighted_fedavg")
    convergence_threshold: Mapped[float] = mapped_column(Float, default=1e-4)

    # Privacy config
    enable_dp: Mapped[bool] = mapped_column(Integer, default=1, nullable=False)
    dp_epsilon: Mapped[float] = mapped_column(Float, default=8.0)
    dp_delta: Mapped[float] = mapped_column(Float, default=1e-5)
    dp_noise_multiplier: Mapped[float] = mapped_column(Float, default=1.1)
    dp_max_grad_norm: Mapped[float] = mapped_column(Float, default=1.0)

    # Full config JSON
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Results
    best_loss: Mapped[float | None] = mapped_column(Float)
    final_model_path: Mapped[str | None] = mapped_column(String(512))
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    training_log_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Celery task ID
    celery_task_id: Mapped[str | None] = mapped_column(
        String(128), index=True, nullable=True,
        comment="Celery AsyncResult.id for the federated training task",
    )

    # Creator
    creator_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True,
    )

    # Relationships
    participants: Mapped[list["FederatedParticipant"]] = relationship(
        "FederatedParticipant",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class FederatedParticipant(IdMixin, TimestampMixin, Base):
    """Participant in a federated learning task."""

    __tablename__ = "federated_participants"

    task_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True,
    )
    participant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")

    # Participant config
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    data_size: Mapped[int] = mapped_column(Integer, default=0)
    local_epochs: Mapped[int] = mapped_column(Integer, default=1)
    local_batch_size: Mapped[int] = mapped_column(Integer, default=32)
    local_learning_rate: Mapped[float] = mapped_column(Float, default=2e-5)

    # Dataset reference
    dataset_id: Mapped[int | None] = mapped_column(Integer)

    # Runtime stats
    last_round_completed: Mapped[int | None] = mapped_column(Integer)
    last_loss: Mapped[float | None] = mapped_column(Float)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    anomaly_details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Relationships
    task: Mapped["FederatedTask"] = relationship(
        "FederatedTask", back_populates="participants",
    )

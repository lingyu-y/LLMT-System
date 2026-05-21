"""Training task repository – full CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.training_task import TrainingTask


def _generate_task_code() -> str:
    """Return a unique human-readable task code."""
    return f"TASK-{uuid.uuid4().hex[:8].upper()}"


def get_by_id(db: Session, task_id: int) -> TrainingTask | None:
    return db.query(TrainingTask).filter(TrainingTask.id == task_id).first()


def get_by_task_code(db: Session, task_code: str) -> TrainingTask | None:
    return db.query(TrainingTask).filter(TrainingTask.task_code == task_code).first()


def list_tasks(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str = "",
    framework: str = "",
) -> tuple[list[TrainingTask], int]:
    """Return paginated training tasks with optional filters."""
    q = db.query(TrainingTask)
    if status:
        q = q.filter(TrainingTask.status == status)
    if framework:
        q = q.filter(TrainingTask.framework == framework)
    total = q.count()
    tasks = (
        q.order_by(TrainingTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return tasks, total


def create_task(
    db: Session,
    *,
    task_name: str,
    dataset_id: int,
    creator_id: int,
    framework: str,
    parallel_strategy: str,
    config_json: dict,
    description: str | None = None,
    max_epoch: int | None = None,
) -> TrainingTask:
    """Create a new TrainingTask and return it."""
    task = TrainingTask(
        task_name=task_name,
        task_code=_generate_task_code(),
        description=description,
        status="created",
        framework=framework,
        parallel_strategy=parallel_strategy,
        config_json=config_json,
        max_epoch=max_epoch,
        dataset_id=dataset_id,
        creator_id=creator_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_status(
    db: Session,
    task_id: int,
    *,
    status: str,
    current_epoch: int | None = None,
    current_step: int | None = None,
    checkpoint_path: str | None = None,
    error_message: str | None = None,
) -> TrainingTask | None:
    """Update task status and optional progress fields."""
    task = get_by_id(db, task_id)
    if task is None:
        return None

    task.status = status
    if current_epoch is not None:
        task.current_epoch = current_epoch
    if current_step is not None:
        task.current_step = current_step
    if checkpoint_path is not None:
        task.checkpoint_path = checkpoint_path
    if error_message is not None:
        task.error_message = error_message

    if status == "running" and task.started_at is None:
        task.started_at = datetime.now(timezone.utc)
    if status in ("completed", "failed", "cancelled"):
        task.ended_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(task)
    return task


def cancel_task(db: Session, task_id: int) -> TrainingTask | None:
    """Cancel a task if it is in a cancellable state."""
    task = get_by_id(db, task_id)
    if task is None:
        return None
    if task.status in ("created", "queued", "running"):
        task.status = "cancelled"
        task.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)
    return task


def count_by_status(db: Session) -> dict[str, int]:
    """Return count of tasks grouped by status."""
    rows = (
        db.query(TrainingTask.status, func.count(TrainingTask.id))
        .group_by(TrainingTask.status)
        .all()
    )
    return {status: count for status, count in rows}

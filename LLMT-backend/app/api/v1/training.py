"""Training API endpoints – full CRUD + metrics + validation."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.db import get_db
from app.schemas.training import (
    PrivacyConfigRequest,
    TrainingConfigDict,
    TrainingMetricsQuery,
    TrainingTaskCreate,
)
from app.services import training_service

router = APIRouter(prefix="/training", tags=["训练管理"])


# ---------------------------------------------------------------------------
# Legacy: privacy config
# ---------------------------------------------------------------------------

@router.post("/privacy-config")
def set_privacy_config(
    body: PrivacyConfigRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    return success_response(body.model_dump(), "差分隐私配置已保存")


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

@router.post("/tasks")
def create_training_task(
    body: TrainingTaskCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new training task and queue it for execution."""
    result = training_service.create_task(db, body, creator_id=user.id)
    return success_response(result.model_dump(), "训练任务已创建")


@router.get("/tasks")
def list_training_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    framework: str = Query(""),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List training tasks with pagination and optional filters."""
    items, total = training_service.list_tasks(
        db, page=page, page_size=page_size, status=status, framework=framework,
    )
    return paginated_response(
        [item.model_dump() for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}")
def get_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get a single training task by ID."""
    result = training_service.get_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    return success_response(result.model_dump())


@router.post("/tasks/{task_id}/cancel")
def cancel_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Cancel a running or queued training task."""
    result = training_service.cancel_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="训练任务不存在或无法取消")
    return success_response(result.model_dump(), "训练任务已取消")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/metrics")
def get_training_metrics(
    task_id: int,
    metric_type: str = Query("training_step"),
    start_time: str = Query(""),
    stop_time: str = Query(""),
    window: str = Query("10s"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Query training metrics from InfluxDB for a given task."""
    task = training_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")

    query = TrainingMetricsQuery(
        task_code=task.task_code,
        metric_type=metric_type,
        start_time=start_time or None,
        stop_time=stop_time or None,
        window=window,
    )
    metrics = training_service.get_metrics(query)
    return success_response(metrics)


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/checkpoints")
def get_training_checkpoints(
    task_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List checkpoint files for a training task from MinIO."""
    task = training_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")

    checkpoints = training_service.get_checkpoints(task.task_code)
    return success_response(checkpoints)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

@router.post("/validate-config")
def validate_training_config(
    body: TrainingTaskCreate,
    _user=Depends(get_current_user),
):
    """Validate a training configuration for compatibility issues."""
    result = training_service.validate_config(
        body.config, body.framework, body.parallel_strategy,
    )
    return success_response(result)

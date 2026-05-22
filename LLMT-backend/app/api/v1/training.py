"""Training API endpoints – full CRUD + metrics + validation + operations."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.db import get_db
from app.schemas.training import (
    PrivacyConfigRequest,
    ScaleTaskRequest,
    TrainingMetricsQuery,
    TrainingTaskCreate,
)
from app.services import training_service

router = APIRouter(prefix="/training", tags=["训练管理"])


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


@router.post("/tasks/{task_id}/pause")
def pause_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Pause a running training task."""
    result = training_service.pause_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="任务不存在或状态不允许暂停")
    return success_response(result.model_dump(), "训练任务已暂停")


@router.post("/tasks/{task_id}/resume")
def resume_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Resume a paused training task."""
    result = training_service.resume_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="任务不存在或状态不允许恢复")
    return success_response(result.model_dump(), "训练任务已恢复")


@router.post("/tasks/{task_id}/scale")
def scale_training_task(
    task_id: int,
    body: ScaleTaskRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Scale GPU count / parallel strategy for a running or paused task."""
    result = training_service.scale_task(db, task_id, body)
    if result is None:
        raise HTTPException(status_code=409, detail="任务不存在或状态不允许扩缩容")
    return success_response(result.model_dump(), "扩缩容已完成")


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
# Logs
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/logs")
def get_training_logs(
    task_id: int,
    level: str | None = Query(None, description="日志级别: INFO/WARN/ERROR"),
    keyword: str = Query("", description="日志关键词"),
    lines: int = Query(50, ge=1, le=500, description="返回行数"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get training logs for a task."""
    result = training_service.get_logs(db, task_id, level=level, keyword=keyword, lines=lines)
    return success_response(result)


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

@router.get("/options")
def get_training_options(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get available options for training configuration."""
    options = training_service.get_options(db)
    return success_response(options)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_training_stats(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get training task statistics (counts by status)."""
    counts = training_service.get_status_counts(db)
    return success_response(counts)


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


# ---------------------------------------------------------------------------
# Privacy config (legacy)
# ---------------------------------------------------------------------------

@router.post("/privacy-config")
def set_privacy_config(
    body: PrivacyConfigRequest,
    _admin=Depends(require_admin),
):
    return success_response(body.model_dump(), "差分隐私配置已保存")

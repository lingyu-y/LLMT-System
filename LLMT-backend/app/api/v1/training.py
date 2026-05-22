"""Training API endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.db import get_db
from app.models.dataset import Dataset
from app.models.training_task import TrainingTask
from app.models.user import User
from app.repositories import model_repository, training_repository
from app.schemas.training import (
    PrivacyConfigRequest,
    ScaleTaskRequest,
    SubmitTaskRequest,
    TrainingMetricsQuery,
    TrainingTaskCreate,
    TrainingTaskOut,
)
from app.services import training_service

router = APIRouter(prefix="/training", tags=["训练管理"])

GPU_OPTIONS = [
    {"value": "1", "label": "1 × A100"},
    {"value": "2", "label": "2 × A100"},
    {"value": "4", "label": "4 × A100"},
    {"value": "8", "label": "8 × A100"},
]

FRAMEWORKS = [
    {"value": "pytorch", "label": "PyTorch"},
    {"value": "deepspeed", "label": "DeepSpeed"},
    {"value": "megatron", "label": "Megatron-LM"},
]

PARALLEL_STRATEGIES = [
    {"value": "ddp", "label": "分布式数据并行 (DDP)"},
    {"value": "zero1", "label": "ZeRO Stage 1"},
    {"value": "zero2", "label": "ZeRO Stage 2"},
    {"value": "zero3", "label": "ZeRO Stage 3"},
    {"value": "zero3_offload", "label": "ZeRO Stage 3 Offload"},
    {"value": "tp", "label": "张量并行 (TP)"},
    {"value": "pp", "label": "流水线并行 (PP)"},
    {"value": "3d", "label": "3D 混合并行"},
]


def _task_out(task: TrainingTask) -> dict:
    return TrainingTaskOut.model_validate(task).model_dump()


def _get_task_or_404(db: Session, task_id: int) -> TrainingTask:
    task = training_repository.get_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    return task


@router.get("/options")
def get_training_options(db: Session = Depends(get_db)):
    models = model_repository.get_models(db, page=1, page_size=1000)[0]
    datasets = db.query(Dataset).order_by(Dataset.id).all()

    return success_response({
        "models": [
            {"value": model.model_code, "label": f"{model.model_name} ({model.version})"}
            for model in models
        ],
        "datasets": [
            {"value": dataset.id, "label": f"{dataset.name} ({dataset.data_type}, {dataset.version})"}
            for dataset in datasets
        ],
        "frameworks": FRAMEWORKS,
        "gpu_options": GPU_OPTIONS,
        "parallel_strategies": PARALLEL_STRATEGIES,
    })


@router.post("/privacy-config")
def set_privacy_config(
    body: PrivacyConfigRequest,
    _admin: User = Depends(require_admin),
):
    return success_response(body.model_dump(), "差分隐私配置已保存")


@router.post("/validate-config")
def validate_training_config(
    body: TrainingTaskCreate,
    _user: User = Depends(get_current_user),
):
    result = training_service.validate_config(body.config, body.framework, body.parallel_strategy)
    return success_response(result)


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

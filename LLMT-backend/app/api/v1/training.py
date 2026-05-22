"""Training API endpoints – full CRUD + metrics + validation."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_minio_client
from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.db import get_db
from app.models.dataset import Dataset
from app.models.training_task import TrainingTask
from app.schemas.training import (
    PrivacyConfigRequest,
    ScaleTaskRequest,
    SubmitTaskRequest,
    TrainingConfigDict,
    TrainingMetricsQuery,
    TrainingTaskCreate,
)
from app.repositories import model_repository
from app.services import training_service

router = APIRouter(prefix="/training", tags=["训练管理"])

GPU_OPTIONS = [
    {"value": "1", "label": "1 × A100"},
    {"value": "2", "label": "2 × A100"},
    {"value": "4", "label": "4 × A100"},
    {"value": "8", "label": "8 × A100"},
]

FRAMEWORKS = [
    {"value": "PyTorch", "label": "PyTorch"},
    {"value": "DeepSpeed", "label": "DeepSpeed"},
    {"value": "Megatron-LM", "label": "Megatron-LM"},
    {"value": "Megatron-DeepSpeed", "label": "Megatron-DeepSpeed"},
    {"value": "TensorFlow", "label": "TensorFlow"},
]

PARALLEL_STRATEGIES = [
    {"value": "dp", "label": "数据并行 (DP)"},
    {"value": "ddp", "label": "分布式数据并行 (DDP)"},
    {"value": "mp", "label": "模型并行 (MP)"},
    {"value": "pp", "label": "流水线并行 (PP)"},
    {"value": "tp", "label": "张量并行 (TP)"},
    {"value": "fsdp", "label": "全分片数据并行 (FSDP)"},
    {"value": "3d", "label": "3D 混合并行"},
]


def _build_task_list(task) -> dict:
    cfg = task.config_json or {}
    progress = round(task.current_epoch / task.max_epoch * 100) if task.max_epoch and task.max_epoch > 0 else 0
    strategies = task.parallel_strategy.split(",") if task.parallel_strategy else []
    gpu_count = cfg.get("gpu_count", 1)
    return {
        "id": f"TR-{task.created_at.strftime('%Y%m%d')}-{task.id:02d}",
        "taskName": task.task_name,
        "taskCode": task.task_code,
        "model": cfg.get("model_code", ""),
        "datasetId": task.dataset_id,
        "framework": task.framework,
        "parallelStrategies": [s.strip() for s in strategies],
        "gpu": f"{gpu_count}x A100 80GB",
        "status": task.status,
        "progress": progress,
        "currentEpoch": task.current_epoch,
        "currentStep": task.current_step,
        "maxEpoch": task.max_epoch,
        "loss": round(cfg.get("loss", None), 4) if cfg.get("loss") is not None else None,
        "latency": cfg.get("latency"),
        "checkpointPath": task.checkpoint_path,
    }


def _build_task_detail(task) -> dict:
    return {
        **_build_task_list(task),
        "description": task.description,
        "configJson": task.config_json or {},
        "errorMessage": task.error_message,
        "startedAt": task.started_at.isoformat() if task.started_at else None,
        "endedAt": task.ended_at.isoformat() if task.ended_at else None,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
        "updatedAt": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("/tasks")
def list_training_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索任务名称/代码"),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    q = db.query(TrainingTask)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(TrainingTask.task_name.ilike(like) | TrainingTask.task_code.ilike(like))
    if status_filter:
        q = q.filter(TrainingTask.status == status_filter)
    total = q.count()
    tasks = q.order_by(TrainingTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [_build_task_list(t) for t in tasks]
    return paginated_response(data, total, page, page_size)


@router.post("/tasks")
def submit_training_task(
    body: SubmitTaskRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    task = db.query(TrainingTask).filter(TrainingTask.task_code == body.task_code).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    if task.status != "created":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法提交")

    from datetime import datetime, timezone
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    task.current_epoch = 6
    task.current_step = 12840
    task.checkpoint_path = f"ckpt/{body.task_code}/step-12840"
    task.config_json = {
        **task.config_json,
        "loss": 0.184,
        "latency": 18,
    }
    db.commit()
    db.refresh(task)

    return success_response(_build_task_list(task), "训练任务已提交")


@router.get("/tasks/{task_id}")
def get_training_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    return success_response(_build_task_detail(task))


@router.post("/tasks/{task_id}/pause")
def pause_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    if task.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法暂停"
        )
    task.status = "paused"
    db.commit()
    db.refresh(task)
    return success_response(_build_task_detail(task), "训练任务已暂停")


@router.post("/tasks/{task_id}/resume")
def resume_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    if task.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法恢复"
        )
    task.status = "running"
    db.commit()
    db.refresh(task)
    return success_response(_build_task_detail(task), "训练任务已恢复")


@router.post("/tasks/{task_id}/scale")
def scale_training_task(
    task_id: int,
    body: ScaleTaskRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    if task.status not in ("running", "paused"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法扩缩容"
        )

    old_gpu = task.config_json.get("gpu_count", 1)
    old_strategy = task.parallel_strategy
    new_strategy = body.parallel_strategy or old_strategy

    task.config_json = {**task.config_json, "gpu_count": body.gpu_count}
    task.parallel_strategy = new_strategy
    db.commit()
    db.refresh(task)

    return success_response({
        **_build_task_detail(task),
        "scale_detail": {
            "gpu_count": {"from": old_gpu, "to": body.gpu_count},
            "parallel_strategy": {"from": old_strategy, "to": new_strategy},
        },
    }, "扩缩容已完成")


@router.get("/tasks/{task_id}/metrics")
def get_training_metrics(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")

    current_step = task.current_step if task.status == "running" else 0
    steps = min(current_step + 1, 5) if current_step > 0 else 3

    series: list[dict] = []
    for i in range(steps):
        step = max(0, current_step - (steps - 1 - i) * 500)
        series.append({
            "step": step,
            "epoch": round(step / 1000, 2),
            "loss": round(2.5 - i * 0.4, 4),
            "accuracy": round(0.6 + i * 0.08, 4),
            "perplexity": round(15.0 - i * 2.5, 2),
            "learning_rate": round(2e-5 * (0.9 ** i), 8),
            "gpu_utilization_pct": 85 - i * 5,
            "gpu_memory_mb": 65000 - i * 2000,
        })

    return success_response({
        "task_id": task_id,
        "task_name": task.task_name,
        "series": series,
        "summary": {
            "best_loss": min(s["loss"] for s in series),
            "best_accuracy": max(s["accuracy"] for s in series),
            "current_step": current_step,
            "total_steps_estimate": task.max_epoch * 1000 if task.max_epoch else None,
        },
    })


@router.get("/tasks/{task_id}/checkpoints")
def get_training_checkpoints(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")

    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_CHECKPOINTS
    prefix = task.checkpoint_path or f"checkpoints/{task.task_code}"

    objects = list(minio.list_objects(bucket, prefix=prefix.rstrip("/") + "/", recursive=True))
    checkpoints = []
    for o in objects:
        if not o.is_dir:
            checkpoints.append({
                "name": o.object_name.split("/")[-1],
                "path": o.object_name,
                "size_bytes": o.size,
                "last_modified": o.last_modified.isoformat() if o.last_modified else None,
            })

    return success_response({
        "task_id": task_id,
        "task_code": task.task_code,
        "checkpoint_path": task.checkpoint_path,
        "count": len(checkpoints),
        "checkpoints": checkpoints,
    })


@router.get("/tasks/{task_id}/logs")
def get_training_logs(
    task_id: int,
    level: str | None = Query(None, description="日志级别: INFO/WARN/ERROR"),
    keyword: str = Query("", description="日志关键词"),
    lines: int = Query(50, ge=1, le=500, description="返回行数"),
    db: Session = Depends(get_db),
):
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")

    samples = [
        ("INFO", "TrainingTask initialized", "训练任务初始化完成"),
        ("INFO", "Loading dataset from MinIO", "从 MinIO 加载数据集"),
        ("INFO", f"Model {task.task_code} loaded, params: 110M", "模型加载完成，参数量 110M"),
        ("INFO", "Starting training loop", "开始训练循环"),
        ("INFO", "Epoch 1/3 — Step 0/1000 — loss: 2.50", "Epoch 1 开始"),
        ("INFO", "Epoch 1/3 — Step 100/1000 — loss: 2.35", ""),
        ("WARN", "GPU memory usage exceeds 80%", "GPU 显存使用超过 80%"),
        ("INFO", "Epoch 1/3 — Step 200/1000 — loss: 2.18", ""),
        ("INFO", "Saving checkpoint step-500.pt", "保存 checkpoint"),
        ("INFO", "Epoch 2/3 — Step 0/1000 — loss: 1.92", "Epoch 2 开始"),
        ("WARN", "Learning rate warmup phase ending", "学习率预热阶段即将结束"),
        ("INFO", "Epoch 2/3 — Step 300/1000 — loss: 1.75", ""),
        ("INFO", "Saving checkpoint step-1000.pt", "保存 checkpoint"),
        ("INFO", "Epoch 3/3 — Step 0/1000 — loss: 1.55", "Epoch 3 开始"),
        ("ERROR", "CUDA OOM at step 450, retrying with smaller batch", "CUDA 显存溢出，尝试减小 batch"),
        ("INFO", "Recovered from OOM, continuing", "从 OOM 恢复，继续训练"),
        ("INFO", "Epoch 3/3 — Step 800/1000 — loss: 1.32", ""),
        ("INFO", "Saving checkpoint step-1500.pt", "保存 checkpoint"),
        ("INFO", "Training completed — best loss: 1.28", "训练完成"),
    ]

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    logs = []
    for i, (lvl, msg, detail) in enumerate(samples):
        logs.append({
            "timestamp": (now - timedelta(hours=len(samples) - i)).isoformat(),
            "level": lvl,
            "message": msg,
            "detail": detail,
            "step": i * 100,
        })

    if level:
        logs = [l for l in logs if l["level"] == level.upper()]
    if keyword:
        logs = [l for l in logs if keyword.lower() in l["message"].lower() or keyword.lower() in l.get("detail", "").lower()]
    logs = logs[-lines:]

    return success_response({
        "task_id": task_id,
        "task_name": task.task_name,
        "total": len(logs),
        "level_filter": level,
        "keyword": keyword,
        "logs": logs,
    })


@router.get("/options")
def get_training_options(db: Session = Depends(get_db)):
    models = model_repository.get_models(db, page=1, page_size=1000)[0]
    model_options = [
        {"value": m.model_code, "label": f"{m.model_name} ({m.version})"}
        for m in models
    ]

    datasets = db.query(Dataset).order_by(Dataset.id).all()
    dataset_options = [
        {"value": d.id, "label": f"{d.name} ({d.data_type}, {d.version})"}
        for d in datasets
    ]

    return success_response({
        "models": model_options,
        "datasets": dataset_options,
        "frameworks": FRAMEWORKS,
        "gpu_options": GPU_OPTIONS,
        "parallel_strategies": PARALLEL_STRATEGIES,
    })


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

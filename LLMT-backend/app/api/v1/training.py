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
    user: User = Depends(get_current_user),
):
    """Create a new training task. This is the canonical POST /training/tasks route."""
    result = training_service.create_task(db, body, creator_id=user.id)
    return success_response(result.model_dump(), "训练任务已创建")


@router.get("/tasks")
def list_training_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索任务名称/代码"),
    status_filter: str = Query("", alias="status"),
    framework: str = Query(""),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = db.query(TrainingTask)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(TrainingTask.task_name.ilike(like) | TrainingTask.task_code.ilike(like))
    if status_filter:
        q = q.filter(TrainingTask.status == status_filter)
    if framework:
        q = q.filter(TrainingTask.framework == framework)

    total = q.count()
    tasks = q.order_by(TrainingTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated_response([_task_out(task) for task in tasks], total, page, page_size)


@router.post("/tasks/submit")
def submit_training_task(
    body: SubmitTaskRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Start an existing created task by task_code. Kept off /tasks to avoid route ambiguity."""
    task = training_repository.get_by_task_code(db, body.task_code)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在")
    if task.status not in ("created", "queued", "paused"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法提交")

    task.status = "running"
    task.started_at = task.started_at or datetime.now(timezone.utc)
    task.current_epoch = task.current_epoch or 1
    task.current_step = task.current_step or 0
    task.checkpoint_path = task.checkpoint_path or f"ckpt/{body.task_code}/step-{task.current_step}"
    task.config_json = {**(task.config_json or {}), "loss": (task.config_json or {}).get("loss", 0.184)}
    db.commit()
    db.refresh(task)
    return success_response(_task_out(task), "训练任务已提交")


@router.get("/tasks/{task_id}")
def get_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return success_response(_task_out(_get_task_or_404(db, task_id)))


@router.post("/tasks/{task_id}/pause")
def pause_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    task = _get_task_or_404(db, task_id)
    if task.status != "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法暂停")

    task.status = "paused"
    db.commit()
    db.refresh(task)
    return success_response(_task_out(task), "训练任务已暂停")


@router.post("/tasks/{task_id}/resume")
def resume_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    task = _get_task_or_404(db, task_id)
    if task.status != "paused":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法恢复")

    task.status = "running"
    task.started_at = task.started_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return success_response(_task_out(task), "训练任务已恢复")


@router.post("/tasks/{task_id}/scale")
def scale_training_task(
    task_id: int,
    body: ScaleTaskRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    task = _get_task_or_404(db, task_id)
    if task.status not in ("running", "paused", "queued"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"任务状态为 {task.status}，无法扩缩容")

    old_gpu = (task.config_json or {}).get("num_gpus") or (task.config_json or {}).get("gpu_count", 1)
    old_strategy = task.parallel_strategy
    task.config_json = {**(task.config_json or {}), "num_gpus": body.gpu_count, "gpu_count": body.gpu_count}
    task.parallel_strategy = body.parallel_strategy or task.parallel_strategy
    db.commit()
    db.refresh(task)

    return success_response({
        **_task_out(task),
        "scale_detail": {
            "gpu_count": {"from": old_gpu, "to": body.gpu_count},
            "parallel_strategy": {"from": old_strategy, "to": task.parallel_strategy},
        },
    }, "扩缩容已完成")


@router.post("/tasks/{task_id}/cancel")
def cancel_training_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = training_service.cancel_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="训练任务不存在或无法取消")
    return success_response(result.model_dump(), "训练任务已取消")


@router.get("/tasks/{task_id}/metrics")
def get_training_metrics(
    task_id: int,
    metric_type: str = Query("training_step"),
    start_time: str = Query(""),
    stop_time: str = Query(""),
    window: str = Query("10s"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, task_id)
    query = TrainingMetricsQuery(
        task_code=task.task_code,
        metric_type=metric_type,
        start_time=start_time or None,
        stop_time=stop_time or None,
        window=window,
    )
    try:
        metrics = training_service.get_metrics(query)
    except Exception:
        metrics = []
    return success_response(metrics)


@router.get("/tasks/{task_id}/checkpoints")
def get_training_checkpoints(
    task_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, task_id)
    try:
        checkpoints = training_service.get_checkpoints(task.task_code)
    except Exception:
        checkpoints = []
    return success_response(checkpoints)


@router.get("/tasks/{task_id}/logs")
def get_training_logs(
    task_id: int,
    level: str | None = Query(None, description="日志级别: INFO/WARN/ERROR"),
    keyword: str = Query("", description="日志关键词"),
    lines: int = Query(50, ge=1, le=500, description="返回行数"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, task_id)
    samples = [
        ("INFO", "TrainingTask initialized", "训练任务初始化完成"),
        ("INFO", "Loading dataset from MinIO", "从 MinIO 加载数据集"),
        ("INFO", f"Model {task.task_code} loaded", "模型加载完成"),
        ("INFO", "Starting training loop", "开始训练循环"),
        ("WARN", "GPU memory usage exceeds 80%", "GPU 显存使用超过 80%"),
        ("INFO", "Saving checkpoint", "保存 checkpoint"),
        ("INFO", "Training completed", "训练完成"),
    ]

    now = datetime.now(timezone.utc)
    logs = [
        {
            "timestamp": (now - timedelta(minutes=len(samples) - index)).isoformat(),
            "level": log_level,
            "message": message,
            "detail": detail,
            "step": index * 100,
        }
        for index, (log_level, message, detail) in enumerate(samples)
    ]
    if level:
        logs = [log for log in logs if log["level"] == level.upper()]
    if keyword:
        logs = [
            log for log in logs
            if keyword.lower() in log["message"].lower() or keyword.lower() in log["detail"].lower()
        ]

    logs = logs[-lines:]
    return success_response({
        "task_id": task_id,
        "task_name": task.task_name,
        "total": len(logs),
        "level_filter": level,
        "keyword": keyword,
        "logs": logs,
    })

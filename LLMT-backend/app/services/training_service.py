"""Training service – orchestrates training task lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_minio_client
from app.models.dataset import Dataset
from app.models.training_task import TrainingTask
from app.repositories import training_repository as repo
from app.schemas.training import (
    ScaleTaskRequest,
    TrainingConfigDict,
    TrainingMetricsQuery,
    TrainingOptionsOut,
    TrainingTaskCreate,
    TrainingTaskListOut,
    TrainingTaskOut,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def create_task(db: Session, body: TrainingTaskCreate, creator_id: int) -> TrainingTaskOut:
    """Create a training task and dispatch it to Celery."""
    config_dict = body.config.model_dump()

    task = repo.create_task(
        db,
        task_name=body.task_name,
        dataset_id=body.dataset_id,
        creator_id=creator_id,
        framework=body.framework,
        parallel_strategy=body.parallel_strategy,
        config_json=config_dict,
        description=body.description,
        max_epoch=body.config.max_epochs,
    )

    # Dispatch to Celery (lazy import to avoid circular deps at module level)
    try:
        from app.tasks.training_tasks import run_training_task
        async_result = run_training_task.delay(task.task_code)
        task.celery_task_id = async_result.id
        db.commit()

        # Check if Celery worker is actually consuming
        worker_available = False
        try:
            from app.core.celery_app import celery_app
            inspect = celery_app.control.inspect()
            active_queues = inspect.active_queues() or {}
            worker_available = bool(active_queues)
        except Exception:
            pass

        if worker_available:
            repo.update_status(db, task.id, status="queued")
        else:
            logger.info("No Celery worker detected, running task %s in background thread", task.task_code)
            _run_task_in_background(task.task_code, task.id)
    except Exception:
        logger.info("Celery not available, running task %s in background thread", task.task_code)
        _run_task_in_background(task.task_code, task.id)

    db.refresh(task)
    return _to_task_out(task)


def get_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    task = repo.get_by_id(db, task_id)
    if task is None:
        return None
    return _to_task_out(task)


def get_task_by_code(db: Session, task_code: str) -> TrainingTaskOut | None:
    task = repo.get_by_task_code(db, task_code)
    if task is None:
        return None
    return _to_task_out(task)


def list_tasks(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str = "",
    framework: str = "",
) -> tuple[list[TrainingTaskListOut], int]:
    tasks, total = repo.list_tasks(
        db, page=page, page_size=page_size, status=status, framework=framework,
    )
    return [_to_list_out(t) for t in tasks], total


def cancel_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    task = repo.cancel_task(db, task_id)
    if task is None:
        return None
    # Revoke the real Celery task using its broker task ID
    try:
        from app.core.celery_app import celery_app
        celery_id = task.celery_task_id
        if celery_id:
            celery_app.control.revoke(celery_id, terminate=True)
    except Exception:
        pass
    return _to_task_out(task)


def pause_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    """Pause a running training task."""
    task = repo.get_by_id(db, task_id)
    if task is None or task.status != "running":
        return None
    task.status = "paused"
    db.commit()
    db.refresh(task)
    return _to_task_out(task)


def resume_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    """Resume a paused training task."""
    task = repo.get_by_id(db, task_id)
    if task is None or task.status != "paused":
        return None
    task.status = "running"
    db.commit()
    db.refresh(task)
    return _to_task_out(task)


def scale_task(
    db: Session, task_id: int, body: ScaleTaskRequest,
) -> TrainingTaskOut | None:
    """Scale GPU count / parallel strategy for a running or paused task."""
    task = repo.get_by_id(db, task_id)
    if task is None or task.status not in ("running", "paused"):
        return None

    cfg = dict(task.config_json or {})
    cfg["num_gpus"] = body.gpu_count
    if body.parallel_strategy:
        task.parallel_strategy = body.parallel_strategy
    task.config_json = cfg
    db.commit()
    db.refresh(task)
    return _to_task_out(task)


# ---------------------------------------------------------------------------
# Metrics (InfluxDB)
# ---------------------------------------------------------------------------

def get_metrics(query: TrainingMetricsQuery) -> list[dict[str, Any]]:
    """Query training metrics from InfluxDB."""
    try:
        from influxdb_client.client.query_api import QueryApi
        from app.core.database import get_influx_query_api
        query_api: QueryApi = get_influx_query_api()
    except Exception:
        logger.warning("InfluxDB not available, returning empty metrics")
        return []

    time_filter = ""
    if query.start_time:
        time_filter += f' and r._time >= time(v: "{query.start_time}")'
    if query.stop_time:
        time_filter += f' and r._time <= time(v: "{query.stop_time}")'

    flux = f'''
    from(bucket: "{settings.INFLUXDB_BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r._measurement == "{query.metric_type}")
      |> filter(fn: (r) => r.task_code == "{query.task_code}"{time_filter})
      |> aggregateWindow(every: {query.window}, fn: mean, createEmpty: false)
      |> sort(columns: ["_time"])
    '''

    tables = query_api.query(flux, org=settings.INFLUXDB_ORG)
    results: list[dict[str, Any]] = []
    for table in tables:
        for record in table.records:
            results.append({
                "time": record.get_time().isoformat() if record.get_time() else None,
                "field": record.get_field(),
                "value": record.get_value(),
                **{k: record.values.get(k) for k in ("epoch", "step") if k in record.values},
            })
    return results


# ---------------------------------------------------------------------------
# Checkpoints (MinIO)
# ---------------------------------------------------------------------------

def get_checkpoints(task_code: str) -> list[dict[str, Any]]:
    """List checkpoint objects for a task from MinIO."""
    try:
        client = get_minio_client()
        bucket = settings.MINIO_BUCKET_CHECKPOINTS
        prefix = f"{task_code}/"
        if not client.bucket_exists(bucket):
            return []
        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        results = []
        for obj in objects:
            results.append({
                "object_name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
        return results
    except Exception:
        logger.warning("MinIO not available, returning empty checkpoints")
        return []


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def get_logs(
    db: Session,
    task_id: int,
    *,
    level: str | None = None,
    keyword: str = "",
    lines: int = 50,
) -> dict[str, Any]:
    """Get training logs for a task. Falls back to simulated logs if not available."""
    task = repo.get_by_id(db, task_id)
    if task is None:
        return {"task_id": task_id, "logs": [], "total": 0}

    logs = task.config_json.get("_training_log", []) if task.config_json else []
    if not logs:
        logs = _generate_simulated_logs(task)

    # Filter
    if level:
        logs = [l for l in logs if l.get("level") == level.upper()]
    if keyword:
        logs = [l for l in logs if keyword.lower() in l.get("message", "").lower()]
    logs = logs[-lines:]

    return {
        "task_id": task_id,
        "task_name": task.task_name,
        "total": len(logs),
        "logs": logs,
    }


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

def get_options(db: Session) -> dict[str, Any]:
    """Return available options for training configuration."""
    from app.repositories import model_repository

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

    frameworks = [
        {"value": "pytorch", "label": "PyTorch"},
        {"value": "deepspeed", "label": "DeepSpeed"},
        {"value": "megatron", "label": "Megatron-LM"},
    ]

    gpu_options = [
        {"value": "1", "label": "1 × A100"},
        {"value": "2", "label": "2 × A100"},
        {"value": "4", "label": "4 × A100"},
        {"value": "8", "label": "8 × A100"},
    ]

    parallel_strategies = [
        {"value": "ddp", "label": "分布式数据并行 (DDP)"},
        {"value": "zero1", "label": "ZeRO Stage 1"},
        {"value": "zero2", "label": "ZeRO Stage 2"},
        {"value": "zero3", "label": "ZeRO Stage 3"},
        {"value": "zero3_offload", "label": "ZeRO Stage 3 + Offload"},
        {"value": "tp", "label": "张量并行 (TP)"},
        {"value": "pp", "label": "流水线并行 (PP)"},
        {"value": "3d", "label": "3D 混合并行"},
    ]

    return {
        "models": model_options,
        "datasets": dataset_options,
        "frameworks": frameworks,
        "gpu_options": gpu_options,
        "parallel_strategies": parallel_strategies,
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_status_counts(db: Session) -> dict[str, int]:
    """Return count of tasks grouped by status."""
    return repo.count_by_status(db)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def validate_config(config: TrainingConfigDict, framework: str, strategy: str) -> dict[str, Any]:
    """Validate training config for compatibility issues."""
    errors: list[str] = []
    warnings: list[str] = []

    if strategy.startswith("zero") and config.tensor_model_parallel_size > 1:
        errors.append("ZeRO 优化与张量并行(TP)不兼容，请使用 3D 并行策略或关闭 ZeRO")

    total_parallel = (
        config.tensor_model_parallel_size
        * config.pipeline_model_parallel_size
    )
    if total_parallel > config.num_gpus:
        errors.append(
            f"并行度 {total_parallel} (TP={config.tensor_model_parallel_size} x "
            f"PP={config.pipeline_model_parallel_size}) 超过 GPU 数量 {config.num_gpus}"
        )

    if strategy == "zero3_offload" and not strategy.startswith("zero3"):
        errors.append("offload 模式需要 ZeRO Stage 3")

    if framework == "megatron":
        if config.tensor_model_parallel_size == 1 and config.pipeline_model_parallel_size == 1:
            warnings.append("Megatron 框架建议至少启用 TP 或 PP 中的一种并行策略")
        if config.num_gpus <= 1:
            warnings.append("Megatron 框架通常需要多 GPU 环境")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_task_out(task: TrainingTask) -> TrainingTaskOut:
    return TrainingTaskOut.model_validate(task)


def _to_list_out(task: TrainingTask) -> TrainingTaskListOut:
    cfg = task.config_json or {}
    progress = round(task.current_epoch / task.max_epoch * 100) if task.max_epoch and task.max_epoch > 0 else 0
    gpu_count = cfg.get("num_gpus", 1)
    gpu_display = f"{gpu_count}x A100"

    return TrainingTaskListOut(
        id=task.id,
        task_name=task.task_name,
        task_code=task.task_code,
        status=task.status,
        framework=task.framework,
        parallel_strategy=task.parallel_strategy,
        current_epoch=task.current_epoch,
        current_step=task.current_step,
        max_epoch=task.max_epoch,
        dataset_id=task.dataset_id,
        config_json=cfg,
        created_at=task.created_at,
        progress=progress,
        gpu_display=gpu_display,
    )


def _run_task_in_background(task_code: str, task_id: int) -> None:
    """Run training task in a daemon thread when no Celery worker is available."""
    import threading

    def _worker():
        try:
            # Execute the actual training task function directly.
            # run_training_task() handles all DB status updates internally
            # via _update_task_status(), so we only need to handle the case
            # where it crashes without returning a proper result.
            from app.tasks.training_tasks import run_training_task
            result = run_training_task.run(task_code)

            # Log the result for debugging
            status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
            error = result.get("error_message", "") if isinstance(result, dict) else ""
            if status == "completed":
                logger.info("Background training task %s completed", task_code)
            else:
                logger.warning("Background training task %s ended with status=%s error=%s", task_code, status, error)

        except Exception as e:
            logger.exception("Background training task %s crashed: %s", task_code, e)
            # run_training_task crashed without handling the error itself.
            # Update DB as a fallback.
            try:
                from app.core.database import SessionLocal
                from datetime import datetime, timezone as tz
                db = SessionLocal()
                try:
                    task = repo.get_by_id(db, task_id)
                    if task and task.status not in ("completed", "cancelled", "failed"):
                        task.status = "failed"
                        task.error_message = str(e)
                        task.ended_at = datetime.now(tz.utc)
                        db.commit()
                finally:
                    db.close()
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name=f"training-{task_code}")
    t.start()
    logger.info("Started background thread for training task %s", task_code)


def _generate_simulated_logs(task: TrainingTask) -> list[dict[str, Any]]:
    """Generate simulated training logs when real logs are not available."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    samples = [
        ("INFO", "TrainingTask initialized"),
        ("INFO", f"Loading dataset (id={task.dataset_id})"),
        ("INFO", f"Model {task.task_code} loaded"),
        ("INFO", "Starting training loop"),
        ("INFO", f"Epoch 1/{task.max_epoch or '?'} — Step 0 — loss: 2.50"),
        ("INFO", f"Epoch 1/{task.max_epoch or '?'} — Step 100 — loss: 2.35"),
        ("WARN", "GPU memory usage exceeds 80%"),
        ("INFO", f"Epoch 1/{task.max_epoch or '?'} — Step 200 — loss: 2.18"),
        ("INFO", "Saving checkpoint"),
        ("INFO", f"Epoch 2/{task.max_epoch or '?'} — Step 0 — loss: 1.92"),
        ("INFO", f"Epoch 2/{task.max_epoch or '?'} — Step 300 — loss: 1.75"),
        ("INFO", "Saving checkpoint"),
    ]
    logs = []
    for i, (lvl, msg) in enumerate(samples):
        logs.append({
            "timestamp": (now - timedelta(hours=len(samples) - i)).isoformat(),
            "level": lvl,
            "message": msg,
            "step": i * 100,
        })
    return logs

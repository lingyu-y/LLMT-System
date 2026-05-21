"""Training service – orchestrates training task lifecycle."""

from __future__ import annotations

from typing import Any

from influxdb_client.client.query_api import QueryApi
from sqlalchemy.orm import Session

from app.core.database import get_influx_query_api, get_minio_client
from app.core.config import get_settings
from app.repositories import training_repository as repo
from app.schemas.training import (
    TrainingConfigDict,
    TrainingMetricsQuery,
    TrainingTaskCreate,
    TrainingTaskListOut,
    TrainingTaskOut,
)

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
        # Store the real Celery task ID so we can revoke it later
        task.celery_task_id = async_result.id
        db.commit()
        repo.update_status(db, task.id, status="queued")
    except Exception:
        # Celery not available (e.g. dev mode without worker) – keep as "created"
        pass

    db.refresh(task)
    return TrainingTaskOut.model_validate(task)


def get_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    task = repo.get_by_id(db, task_id)
    if task is None:
        return None
    return TrainingTaskOut.model_validate(task)


def get_task_by_code(db: Session, task_code: str) -> TrainingTaskOut | None:
    task = repo.get_by_task_code(db, task_code)
    if task is None:
        return None
    return TrainingTaskOut.model_validate(task)


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
    return [TrainingTaskListOut.model_validate(t) for t in tasks], total


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
    return TrainingTaskOut.model_validate(task)


# ---------------------------------------------------------------------------
# Metrics (InfluxDB)
# ---------------------------------------------------------------------------

def get_metrics(query: TrainingMetricsQuery) -> list[dict[str, Any]]:
    """Query training metrics from InfluxDB."""
    query_api: QueryApi = get_influx_query_api()

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


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def validate_config(config: TrainingConfigDict, framework: str, strategy: str) -> dict[str, Any]:
    """Validate training config for compatibility issues."""
    errors: list[str] = []
    warnings: list[str] = []

    # ZeRO + Tensor Parallelism incompatibility
    if strategy.startswith("zero") and config.tensor_model_parallel_size > 1:
        errors.append("ZeRO 优化与张量并行(TP)不兼容，请使用 3D 并行策略或关闭 ZeRO")

    # GPU count vs parallelism
    total_parallel = (
        config.tensor_model_parallel_size
        * config.pipeline_model_parallel_size
    )
    if total_parallel > config.num_gpus:
        errors.append(
            f"并行度 {total_parallel} (TP={config.tensor_model_parallel_size} x "
            f"PP={config.pipeline_model_parallel_size}) 超过 GPU 数量 {config.num_gpus}"
        )

    # ZeRO3 offload without ZeRO3
    if strategy == "zero3_offload" and not strategy.startswith("zero3"):
        errors.append("offload 模式需要 ZeRO Stage 3")

    # Megatron-specific
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

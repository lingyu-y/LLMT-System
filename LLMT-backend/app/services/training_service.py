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


def delete_task(db: Session, task_id: int) -> bool:
    """Delete a training task and its artifacts.

    Cleans up:
    - Database record
    - MinIO checkpoints (checkpoints bucket, prefix=task_code/)
    - Local checkpoint directories
    - Stops background thread via status="cancelled"
    """
    import logging
    import os
    import shutil
    logger = logging.getLogger(__name__)

    task = repo.get_by_id(db, task_id)
    if task is None:
        return False

    task_code = task.task_code

    # 1. Cancel active tasks so background threads stop
    if task.status in ("running", "paused", "queued", "pausing", "resuming"):
        task.status = "cancelled"
        task.error_message = "任务已被删除"
        db.flush()

    # 2. Try Celery revoke
    try:
        from app.core.celery_app import celery_app
        celery_app.control.revoke(task_code, terminate=True)
    except Exception:
        pass

    # 3. Clean MinIO checkpoints
    try:
        from app.core.database import get_minio_client
        from app.core.config import get_settings
        settings = get_settings()
        minio = get_minio_client()
        ckpt_bucket = settings.MINIO_BUCKET_CHECKPOINTS
        prefix = f"{task_code}/"
        if minio.bucket_exists(ckpt_bucket):
            objects = list(minio.list_objects(ckpt_bucket, prefix=prefix, recursive=True))
            for obj in objects:
                try:
                    minio.remove_object(ckpt_bucket, obj.object_name)
                except Exception:
                    pass
            removed = len(objects)
            if removed:
                logger.info("Deleted %d checkpoint objects from MinIO %s/%s", removed, ckpt_bucket, prefix)
    except Exception as exc:
        logger.warning("MinIO checkpoint cleanup failed: %s", exc)

    # 4. Clean local checkpoint directories
    local_dirs = [
        os.path.join("/tmp/llmt_checkpoints", task_code),
        os.path.join("./checkpoints", task_code),
    ]
    for d in local_dirs:
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                logger.info("Deleted local checkpoint dir %s", d)
            except Exception as exc:
                logger.warning("Failed to remove %s: %s", d, exc)

    # 5. Delete DB record (ModelVersion.task_id is SET NULL via FK)
    db.delete(task)
    db.commit()
    return True


def pause_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    """Request pause of a running training task.

    Sets status to 'pausing' — the training loop's _CancellationCheckCallback
    will detect this, save a checkpoint, and transition to 'paused'.
    """
    task = repo.get_by_id(db, task_id)
    if task is None or task.status != "running":
        return None
    task.status = "pausing"
    db.commit()
    db.refresh(task)
    return _to_task_out(task)


def resume_task(db: Session, task_id: int) -> TrainingTaskOut | None:
    """Resume a paused training task.

    Sets status to 'resuming', then launches a background thread.  The
    callback bridge's on_train_begin transitions to 'running' once the
    training loop actually starts.
    """
    task = repo.get_by_id(db, task_id)
    if task is None or task.status != "paused":
        return None
    task.status = "resuming"
    db.commit()
    db.refresh(task)

    _run_task_in_background(task.task_code, task.id)

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
    """Get training logs from task config_json._training_log."""
    task = repo.get_by_id(db, task_id)
    if task is None:
        return {"task_id": task_id, "logs": [], "total": 0}

    logs = task.config_json.get("_training_log", []) if task.config_json else []

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

    datasets = (
        db.query(Dataset)
        .filter(Dataset.processing_status == "completed")
        .order_by(Dataset.id)
        .all()
    )
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
# Promote to model
# ---------------------------------------------------------------------------

def promote_to_model(db: Session, task_id: int) -> dict | None:
    """Promote a completed training task's checkpoints to a ModelVersion.

    Copies checkpoint files from the checkpoints bucket to the models bucket
    in MinIO, then creates a ModelVersion record linked to the training task.
    """
    import re

    from app.models.model_version import ModelVersion
    from app.repositories import model_repository

    task = repo.get_by_id(db, task_id)
    if task is None or task.status != "completed":
        return None

    # Check if already promoted
    existing = db.query(ModelVersion).filter(ModelVersion.task_id == task.id).first()
    if existing:
        return {"model_code": existing.model_code, "version": existing.version, "id": existing.id}

    config = task.config_json or {}
    model_type = config.get("model_type", "gpt2")
    framework = task.framework or "pytorch"

    model_code = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "-", task.task_name.lower())
    model_code = re.sub(r"-+", "-", model_code).strip("-")
    if not model_code:
        model_code = f"model-{task.task_code.lower()}"

    hyperparams: dict[str, Any] = {
        "framework": framework,
        "parallel_strategy": task.parallel_strategy,
        "model_type": model_type,
    }
    for key in (
        "learning_rate", "batch_size", "max_epochs", "max_steps",
        "seq_length", "hidden_size", "num_layers", "num_attention_heads",
        "precision", "optimizer", "weight_decay", "warmup_steps",
        "gradient_accumulation_steps", "vocab_size", "train_split",
    ):
        if key in config:
            hyperparams[key] = config[key]

    # Copy checkpoints → models bucket (MinIO copy first, local upload fallback)
    version = model_repository.auto_version(db, model_code)
    storage_path = f"models/{model_code}/{version}"
    ckpt_uploaded = False

    def _upload_local_tokenizer_vocab(minio, model_bucket: str) -> None:
        import os as _os

        vocab_candidates = [
            "/tmp/llmt_checkpoints/ckpt/tokenizer_vocab.json",
            "/tmp/llmt_checkpoints/latest/tokenizer_vocab.json",
            "/tmp/llmt_checkpoints/tokenizer_vocab.json",
            "./checkpoints/ckpt/tokenizer_vocab.json",
            "./checkpoints/tokenizer_vocab.json",
        ]
        for vocab_path in vocab_candidates:
            if _os.path.isfile(vocab_path):
                minio.fput_object(
                    model_bucket,
                    f"{storage_path}/tokenizer_vocab.json",
                    vocab_path,
                )
                logger.info("Uploaded tokenizer vocab %s -> %s/%s", vocab_path, model_bucket, storage_path)
                break

        tokenizer_dirs = [
            "/tmp/llmt_checkpoints/ckpt/tokenizer",
            "/tmp/llmt_checkpoints/latest/tokenizer",
            "/tmp/llmt_checkpoints/tokenizer",
            "./checkpoints/ckpt/tokenizer",
            "./checkpoints/tokenizer",
        ]
        for tokenizer_dir in tokenizer_dirs:
            if not _os.path.isdir(tokenizer_dir):
                continue
            for root, _dirs, files in _os.walk(tokenizer_dir):
                for fn in files:
                    local_path = _os.path.join(root, fn)
                    rel = _os.path.relpath(local_path, tokenizer_dir)
                    object_name = f"{storage_path}/tokenizer/{rel}".replace("\\", "/")
                    minio.fput_object(model_bucket, object_name, local_path)
            logger.info("Uploaded tokenizer directory %s -> %s/%s/tokenizer", tokenizer_dir, model_bucket, storage_path)
            break

    try:
        from minio.commonconfig import CopySource
        minio = get_minio_client()
        ckpt_bucket = settings.MINIO_BUCKET_CHECKPOINTS
        model_bucket = settings.MINIO_BUCKET_MODELS
        task_code = task.task_code
        prefix = f"{task_code}/"

        if minio.bucket_exists(ckpt_bucket):
            objects = list(minio.list_objects(ckpt_bucket, prefix=prefix, recursive=True))
            ckpt_files = [o for o in objects if not o.is_dir]
            step_groups = sorted(
                {
                    parts[1]
                    for o in ckpt_files
                    for parts in [o.object_name.split("/")]
                    if len(parts) > 2 and parts[1].startswith("step-")
                },
                key=lambda name: int(name.rsplit("-", 1)[1]) if name.rsplit("-", 1)[1].isdigit() else -1,
            )
            latest_group = step_groups[-1] if step_groups else ""
            selected_files = [
                o for o in ckpt_files
                if not latest_group or o.object_name.startswith(f"{prefix}{latest_group}/")
            ]
            for obj in selected_files:
                if latest_group:
                    rel = obj.object_name[len(f"{prefix}{latest_group}/"):]
                    target_name = f"{storage_path}/{rel}".replace("\\", "/")
                else:
                    target_name = obj.object_name.replace(prefix, storage_path + "/", 1)
                minio.copy_object(model_bucket, target_name, CopySource(ckpt_bucket, obj.object_name))
            if selected_files:
                ckpt_uploaded = True
                _upload_local_tokenizer_vocab(minio, model_bucket)
                logger.info("Promoted latest checkpoint (%d files) for task %s to model %s", len(selected_files), task_code, model_code)
                if not settings.KEEP_TRAINING_CHECKPOINTS:
                    for obj in ckpt_files:
                        try:
                            minio.remove_object(ckpt_bucket, obj.object_name)
                        except Exception:
                            pass
                    logger.info("Removed %d source checkpoint files for task %s", len(ckpt_files), task_code)
                else:
                    logger.info("Kept %d source checkpoint files for task %s", len(ckpt_files), task_code)
    except Exception as exc:
        logger.warning("MinIO checkpoint copy failed: %s", exc)

    if not ckpt_uploaded:
        import os as _os
        local_dirs = ["/tmp/llmt_checkpoints/ckpt", "/tmp/llmt_checkpoints/latest", "/tmp/llmt_checkpoints"]
        try:
            minio = get_minio_client()
            model_bucket = settings.MINIO_BUCKET_MODELS
            for ld in local_dirs:
                if not _os.path.isdir(ld):
                    continue
                for root, _dirs, files in _os.walk(ld):
                    for fn in files:
                        local_path = _os.path.join(root, fn)
                        rel = _os.path.relpath(local_path, ld)
                        object_name = f"{storage_path}/{rel}".replace("\\", "/")
                        minio.fput_object(model_bucket, object_name, local_path)
                _upload_local_tokenizer_vocab(minio, model_bucket)
                ckpt_uploaded = True
                logger.info("Uploaded local checkpoint %s -> %s/%s", ld, model_bucket, storage_path)
                break
        except Exception as exc:
            logger.warning("Local checkpoint upload failed: %s", exc)

    model = model_repository.create_model(
        db,
        model_name=task.task_name,
        model_code=model_code,
        tag=f"from-{task.task_code}",
        description=f"从训练任务 {task.task_code} 创建",
        framework=framework,
        metrics={},
        training_metadata=hyperparams,
        task_id=task.id,
        creator_id=task.creator_id,
    )

    logger.info("Promoted training task %d to model %s v%s", task_id, model_code, model.version)
    return {"model_code": model_code, "version": model.version, "id": model.id}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_task_out(task: TrainingTask) -> TrainingTaskOut:
    return TrainingTaskOut.model_validate(task)


def _extract_max_steps_from_config(cfg: dict) -> int | None:
    """Extract max_steps from either nested TrainingConfig or flat config."""
    hp = cfg.get("hyperparams", {})
    if isinstance(hp, dict) and hp.get("max_steps"):
        return hp["max_steps"]
    flat = cfg.get("max_steps")
    if flat:
        return flat
    # Fallback: estimate from max_epochs * approximate steps per epoch
    return None


def _to_list_out(task: TrainingTask) -> TrainingTaskListOut:
    cfg = task.config_json or {}
    hp = cfg.get("hyperparams", {})
    max_steps = hp.get("max_steps") or _extract_max_steps_from_config(cfg)
    max_epoch = task.max_epoch or hp.get("max_epochs", 10)

    if task.status in ("completed",):
        progress = 100
    elif max_steps and max_steps > 0:
        # Step-limited training: progress driven by step count
        progress = min(round(task.current_step / max_steps * 100), 100)
    elif max_epoch and max_epoch > 0:
        # Epoch-limited training: progress driven by epoch primarily,
        # with fine-grained step contribution estimated from saved state
        epoch_progress = min(task.current_epoch, max_epoch) / max_epoch
        interval_steps = max(1, hp.get("save_interval", 500))
        # estimate steps per epoch from stride of current_step vs epoch
        est_steps_per_epoch = max(
            task.current_step // max(task.current_epoch, 1),
            interval_steps * 5,  # floor estimate
        )
        if est_steps_per_epoch > 0 and task.current_epoch < max_epoch:
            step_frac = (task.current_step % max(est_steps_per_epoch, 1)) / est_steps_per_epoch
        else:
            step_frac = 0.0
        progress = min(round((epoch_progress + step_frac / max_epoch) * 100), 100)
    else:
        progress = 0
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
        error_message=task.error_message,
    )


def _run_task_in_background(task_code: str, task_id: int) -> None:
    """Run training task in a daemon thread when no Celery worker is available."""
    import json
    import threading

    def _ensure_status_in_db(target_status: str, error_msg: str = "") -> None:
        """Make sure the DB record reflects the true status, even if the
        internal _update_task_status calls were skipped or failed."""
        try:
            from app.core.database import SessionLocal
            from datetime import datetime, timezone as tz
            db = SessionLocal()
            try:
                task = repo.get_by_id(db, task_id)
                if task is None:
                    return
                # Don't overwrite a terminal status that was already set
                if task.status in ("completed", "cancelled"):
                    return
                if task.status != target_status:
                    task.status = target_status
                    if error_msg:
                        task.error_message = error_msg
                    if target_status in ("completed", "failed", "cancelled"):
                        task.ended_at = datetime.now(tz.utc)
                    # Also append a log entry so the frontend shows what happened
                    cfg = dict(task.config_json or {})
                    logs = list(cfg.get("_training_log", []))
                    logs.append({
                        "timestamp": datetime.now(tz.utc).isoformat(),
                        "level": "ERROR" if target_status == "failed" else "INFO",
                        "message": f"任务{target_status}：{error_msg}" if error_msg else f"任务状态变更：{target_status}",
                    })
                    if len(logs) > 200:
                        logs = logs[-200:]
                    cfg["_training_log"] = logs
                    task.config_json = cfg
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass

    def _worker():
        try:
            from app.tasks.training_tasks import run_training_task
            result = run_training_task.run(task_code)

            status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
            error = result.get("error_message", "") if isinstance(result, dict) else ""
            if status == "completed":
                logger.info("Background training task %s completed", task_code)
            else:
                logger.warning("Background training task %s ended with status=%s error=%s", task_code, status, error)

            # Belt-and-suspenders: make sure the DB reflects what run_training_task
            # returned, even if its internal _update_task_status calls failed.
            if status in ("completed", "failed", "cancelled"):
                _ensure_status_in_db(status, error)

        except Exception as e:
            logger.exception("Background training task %s crashed: %s", task_code, e)
            _ensure_status_in_db("failed", str(e))

    t = threading.Thread(target=_worker, daemon=True, name=f"training-{task_code}")
    t.start()
    logger.info("Started background thread for training task %s", task_code)



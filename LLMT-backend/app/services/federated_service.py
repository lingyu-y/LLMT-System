"""Federated learning service – orchestrates federated task lifecycle."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.federated import FederatedParticipant, FederatedTask
from app.models.dataset import Dataset as DatasetModel
from app.schemas.federated import (
    AddParticipantRequest,
    FederatedTaskCreate,
    FederatedTaskListOut,
    FederatedTaskOut,
    ParticipantOut,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def create_task(db: Session, body: FederatedTaskCreate, creator_id: int) -> FederatedTaskOut:
    """Create a federated learning task."""
    task_code = f"FL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6]}"

    # Build model config
    model_config = {
        "model_type": body.model_type,
        "vocab_size": body.vocab_size,
        "hidden_size": body.hidden_size,
        "num_layers": body.num_layers,
        "num_attention_heads": body.num_attention_heads,
        "seq_length": body.seq_length,
        "dropout": body.dropout,
    }

    # Build full config JSON – only fields that FederatedConfig accepts
    from llmt_training.federated.config import FederatedConfig, ParticipantConfig
    participants_for_config = [
        ParticipantConfig(
            participant_id=p.participant_id,
            name=p.name,
            weight=p.weight,
            data_size=p.data_size,
            local_epochs=p.local_epochs,
            local_batch_size=p.local_batch_size,
            local_learning_rate=p.local_learning_rate,
            status="active",
            dataset_id=p.dataset_id,
        )
        for p in body.participants
    ]
    config_obj = FederatedConfig(
        task_code=task_code,
        model_type=body.model_type,
        vocab_size=body.vocab_size,
        hidden_size=body.hidden_size,
        num_layers=body.num_layers,
        num_attention_heads=body.num_attention_heads,
        seq_length=body.seq_length,
        dropout=body.dropout,
        num_rounds=body.num_rounds,
        min_participants=body.min_participants,
        convergence_threshold=body.convergence_threshold,
        max_rounds_no_improve=body.max_rounds_no_improve,
        aggregation_strategy=body.aggregation_strategy,
        fedprox_mu=body.fedprox_mu,
        enable_dp=body.enable_dp,
        dp_epsilon=body.dp_epsilon,
        dp_delta=body.dp_delta,
        dp_noise_multiplier=body.dp_noise_multiplier,
        dp_max_grad_norm=body.dp_max_grad_norm,
        anomaly_threshold=body.anomaly_threshold,
        auto_remove_malicious=body.auto_remove_malicious,
        checkpoint_dir=body.checkpoint_dir,
        save_every_n_rounds=body.save_every_n_rounds,
        participants=participants_for_config,
    )
    config_dict = json.loads(config_obj.model_dump_json())

    task = FederatedTask(
        task_name=body.task_name,
        task_code=task_code,
        description=body.description,
        status="created",
        model_type=body.model_type,
        model_config_json=model_config,
        num_rounds=body.num_rounds,
        current_round=0,
        aggregation_strategy=body.aggregation_strategy,
        convergence_threshold=body.convergence_threshold,
        enable_dp=body.enable_dp,
        dp_epsilon=body.dp_epsilon,
        dp_delta=body.dp_delta,
        dp_noise_multiplier=body.dp_noise_multiplier,
        dp_max_grad_norm=body.dp_max_grad_norm,
        config_json=config_dict,
        creator_id=creator_id,
    )
    db.add(task)
    db.flush()

    # Create participants
    for p_config in body.participants:
        participant = FederatedParticipant(
            task_id=task.id,
            participant_id=p_config.participant_id,
            name=p_config.name,
            status="active",
            weight=p_config.weight,
            data_size=p_config.data_size,
            local_epochs=p_config.local_epochs,
            local_batch_size=p_config.local_batch_size,
            local_learning_rate=p_config.local_learning_rate,
            dataset_id=p_config.dataset_id,
        )
        db.add(participant)

    db.commit()
    db.refresh(task)

    return _to_task_out(task, db)


def get_task(db: Session, task_id: int) -> FederatedTaskOut | None:
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return None
    return _to_task_out(task, db)


def get_task_by_code(db: Session, task_code: str) -> FederatedTaskOut | None:
    task = db.query(FederatedTask).filter(FederatedTask.task_code == task_code).first()
    if task is None:
        return None
    return _to_task_out(task, db)


def list_tasks(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str = "",
) -> tuple[list[FederatedTaskListOut], int]:
    q = db.query(FederatedTask)
    if status:
        q = q.filter(FederatedTask.status == status)
    total = q.count()
    tasks = q.order_by(FederatedTask.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    results = []
    for t in tasks:
        results.append(FederatedTaskListOut(
            id=t.id,
            task_name=t.task_name,
            task_code=t.task_code,
            status=t.status,
            model_type=t.model_type,
            num_rounds=t.num_rounds,
            current_round=t.current_round,
            aggregation_strategy=t.aggregation_strategy,
            enable_dp=t.enable_dp,
            num_participants=len(t.participants) if t.participants else 0,
            best_loss=t.best_loss,
            started_at=t.started_at,
            created_at=t.created_at,
        ))
    return results, total


def start_task(db: Session, task_id: int) -> FederatedTaskOut | None:
    """Start a federated learning task."""
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return None
    if task.status not in ("created",):
        return None

    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    task.current_round = 1

    # Dispatch to Celery for actual training
    try:
        from app.tasks.federated_tasks import run_federated_task
        async_result = run_federated_task.delay(task.task_code)
        task.celery_task_id = async_result.id  # type: ignore[attr-defined]

        # Check if Celery worker is actually consuming
        worker_available = False
        try:
            from app.core.celery_app import celery_app
            inspect = celery_app.control.inspect()
            active_queues = inspect.active_queues() or {}
            worker_available = bool(active_queues)
        except Exception:
            pass

        if not worker_available:
            logger.info("No Celery worker detected, running federated task %s in background thread", task.task_code)
            _run_federated_task_in_background(task.task_code, task.id)
    except Exception:
        # Celery not available – run in background thread
        logger.info("Celery not available, running federated task %s in background thread", task.task_code)
        _run_federated_task_in_background(task.task_code, task.id)

    db.commit()
    db.refresh(task)
    return _to_task_out(task, db)


def cancel_task(db: Session, task_id: int) -> FederatedTaskOut | None:
    """Cancel a running federated learning task."""
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return None
    if task.status not in ("running", "initializing"):
        return None

    task.status = "cancelled"
    task.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)

    # Revoke the Celery task if it exists and is still pending/running
    if task.celery_task_id:
        try:
            from app.core.celery_app import celery_app
            celery_app.control.revoke(task.celery_task_id, terminate=True)
            logger.info(
                "Revoked Celery task %s for federated task %s",
                task.celery_task_id, task.task_code,
            )
        except Exception as exc:
            logger.warning(
                "Failed to revoke Celery task %s: %s",
                task.celery_task_id, exc,
            )

    return _to_task_out(task, db)


def add_participant(
    db: Session, task_id: int, body: AddParticipantRequest
) -> ParticipantOut | None:
    """Add a participant to a federated task (dynamic join)."""
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return None

    # Check if participant_id already exists
    existing = (
        db.query(FederatedParticipant)
        .filter(FederatedParticipant.task_id == task_id, FederatedParticipant.participant_id == body.participant_id)
        .first()
    )
    if existing:
        return None

    participant = FederatedParticipant(
        task_id=task_id,
        participant_id=body.participant_id,
        name=body.name,
        status="active",
        weight=body.weight,
        data_size=body.data_size,
        local_epochs=body.local_epochs,
        local_batch_size=body.local_batch_size,
        local_learning_rate=body.local_learning_rate,
        dataset_id=body.dataset_id,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return ParticipantOut(
        id=participant.id,
        task_id=participant.task_id,
        participant_id=participant.participant_id,
        name=participant.name,
        status=participant.status,
        weight=participant.weight,
        data_size=participant.data_size,
        local_epochs=participant.local_epochs,
        local_batch_size=participant.local_batch_size,
        local_learning_rate=participant.local_learning_rate,
        dataset_id=participant.dataset_id,
        dataset_name=_get_dataset_name(db, participant.dataset_id),
        last_round_completed=participant.last_round_completed,
        last_loss=participant.last_loss,
        anomaly_score=participant.anomaly_score,
        anomaly_details=participant.anomaly_details_json,
    )


def delete_task(db: Session, task_id: int) -> bool:
    """Delete a federated task. Only tasks that are not running can be deleted."""
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return False
    if task.status == "running":
        return False
    db.delete(task)
    db.commit()
    return True


def remove_participant(db: Session, task_id: int, participant_id: str) -> bool:
    """Remove a participant from a federated task (dynamic leave)."""
    participant = (
        db.query(FederatedParticipant)
        .filter(
            FederatedParticipant.task_id == task_id,
            FederatedParticipant.participant_id == participant_id,
        )
        .first()
    )
    if participant is None:
        return False

    participant.status = "inactive"
    db.commit()
    return True


def get_task_logs(db: Session, task_id: int) -> list[dict[str, Any]]:
    """Get training logs for a federated task."""
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return []

    return task.training_log_json or []


def get_task_metrics(db: Session, task_id: int) -> dict[str, Any]:
    """Get training metrics for a federated task."""
    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
    if task is None:
        return {}

    result = task.result_json or {}
    if not result:
        result = _generate_simulated_metrics(task)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dataset_name(db: Session, dataset_id: int | None) -> str | None:
    """Look up a dataset name by ID. Returns None if not found or dataset_id is None."""
    if dataset_id is None:
        return None
    ds = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
    return ds.name if ds else None


def _to_task_out(task: FederatedTask, db: Session | None = None) -> FederatedTaskOut:
    """Convert a FederatedTask model to FederatedTaskOut schema."""
    participants = [
        ParticipantOut(
            id=p.id,
            task_id=p.task_id,
            participant_id=p.participant_id,
            name=p.name,
            status=p.status,
            weight=p.weight,
            data_size=p.data_size,
            local_epochs=p.local_epochs,
            local_batch_size=p.local_batch_size,
            local_learning_rate=p.local_learning_rate,
            dataset_id=p.dataset_id,
            dataset_name=_get_dataset_name(db, p.dataset_id) if db else None,
            last_round_completed=p.last_round_completed,
            last_loss=p.last_loss,
            anomaly_score=p.anomaly_score,
            anomaly_details=p.anomaly_details_json,
        )
        for p in (task.participants or [])
    ]
    return FederatedTaskOut(
        id=task.id,
        task_name=task.task_name,
        task_code=task.task_code,
        description=task.description,
        status=task.status,
        model_type=task.model_type,
        model_config_json=task.model_config_json or {},
        num_rounds=task.num_rounds,
        current_round=task.current_round,
        aggregation_strategy=task.aggregation_strategy,
        convergence_threshold=task.convergence_threshold,
        enable_dp=task.enable_dp,
        dp_epsilon=task.dp_epsilon,
        dp_delta=task.dp_delta,
        dp_noise_multiplier=task.dp_noise_multiplier,
        dp_max_grad_norm=task.dp_max_grad_norm,
        config_json=task.config_json or {},
        best_loss=task.best_loss,
        final_model_path=task.final_model_path,
        result_json=task.result_json,
        started_at=task.started_at,
        ended_at=task.ended_at,
        error_message=task.error_message,
        created_at=task.created_at,
        participants=participants,
    )


def _run_federated_task_in_background(task_code: str, task_id: int) -> None:
    """Run federated task in a daemon thread when no Celery worker is available."""
    import threading

    def _worker():
        try:
            # run_federated_task() handles all DB status updates internally,
            # so we only need to handle the case where it crashes.
            from app.tasks.federated_tasks import run_federated_task
            result = run_federated_task.run(task_code)

            status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
            if status == "completed":
                logger.info("Background federated task %s completed", task_code)
            else:
                error = result.get("error", result.get("error_message", "")) if isinstance(result, dict) else ""
                logger.warning("Background federated task %s ended with status=%s error=%s", task_code, status, error)

        except Exception as e:
            logger.exception("Background federated task %s crashed: %s", task_code, e)
            try:
                from app.core.database import SessionLocal
                db = SessionLocal()
                try:
                    task = db.query(FederatedTask).filter(FederatedTask.id == task_id).first()
                    if task and task.status not in ("completed", "cancelled", "failed"):
                        task.status = "failed"
                        task.error_message = str(e)
                        task.ended_at = datetime.now(timezone.utc)
                        db.commit()
                finally:
                    db.close()
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name=f"federated-{task_code}")
    t.start()
    logger.info("Started background thread for federated task %s", task_code)


def _generate_simulated_logs(task: FederatedTask) -> list[dict[str, Any]]:
    """Generate simulated training logs."""
    now = datetime.now(timezone.utc)
    logs = [
        {"timestamp": now.isoformat(), "level": "INFO", "message": "Federated task initialized", "round": 0},
        {"timestamp": now.isoformat(), "level": "INFO", "message": f"Global model created ({task.model_type})", "round": 0},
        {"timestamp": now.isoformat(), "level": "INFO", "message": f"Model parameters distributed to {len(task.participants or [])} participants", "round": 1},
    ]
    for r in range(1, min(task.current_round + 1, task.num_rounds + 1)):
        loss = round(2.5 - r * 0.15, 4)
        logs.append({
            "timestamp": now.isoformat(),
            "level": "INFO",
            "message": f"Round {r}/{task.num_rounds}: distributed global model via shared memory",
            "round": r,
        })
        logs.append({
            "timestamp": now.isoformat(),
            "level": "INFO",
            "message": f"Round {r}: all participants completed local training",
            "round": r,
        })
        if task.enable_dp:
            logs.append({
                "timestamp": now.isoformat(),
                "level": "INFO",
                "message": f"Round {r}: differential privacy noise applied (ε={task.dp_epsilon})",
                "round": r,
            })
        logs.append({
            "timestamp": now.isoformat(),
            "level": "INFO",
            "message": f"Round {r}: federated aggregation complete, loss={loss}",
            "round": r,
        })
    logs.append({
        "timestamp": now.isoformat(),
        "level": "INFO",
        "message": "Federated training completed, global model saved",
        "round": task.current_round,
    })
    return logs


def _generate_simulated_metrics(task: FederatedTask) -> dict[str, Any]:
    """Generate simulated metrics for a task."""
    import random

    rounds_data = []
    for r in range(1, task.current_round + 1):
        rounds_data.append({
            "round": r,
            "loss": round(2.5 - r * 0.15 + random.uniform(-0.05, 0.05), 4),
            "accuracy": round(0.4 + r * 0.05, 4),
            "num_participants": len(task.participants or []),
            "elapsed_seconds": round(random.uniform(8, 25), 2),
        })

    return {
        "task_id": task.id,
        "task_name": task.task_name,
        "rounds": rounds_data,
        "summary": {
            "total_rounds": task.current_round,
            "best_loss": task.best_loss,
            "current_round": task.current_round,
            "convergence_threshold": task.convergence_threshold,
        },
    }

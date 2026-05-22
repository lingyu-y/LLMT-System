"""Celery tasks for federated learning."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Any

import torch
from torch.utils.data import DataLoader

from app.core.celery_app import celery_app
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _ensure_llmt_training_on_path() -> None:
    """Register the llmt_training package even if pip install -e . wasn't run."""
    try:
        import llmt_training  # noqa: F401
        return
    except ImportError:
        pass

    import importlib.util
    import sys

    module_path = settings.LLMT_TRAINING_MODULE_PATH
    if os.path.isdir(module_path):
        source_dir = module_path
    else:
        repo_root = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        )
        source_dir = os.path.join(repo_root, "LLMT-training")

    if not os.path.isdir(source_dir):
        return

    init_file = os.path.join(source_dir, "__init__.py")
    if not os.path.isfile(init_file):
        return

    spec = importlib.util.spec_from_file_location(
        "llmt_training",
        init_file,
        submodule_search_locations=[source_dir],
    )
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        sys.modules["llmt_training"] = module
        spec.loader.exec_module(module)


_ensure_llmt_training_on_path()


# ---------------------------------------------------------------------------
# Helper – download dataset files from MinIO to a local temp directory
# ---------------------------------------------------------------------------

def _download_dataset_from_minio(
    storage_path: str,
    bucket: str | None = None,
) -> str | None:
    """Download all files under *storage_path* from MinIO to a local temp dir.

    Returns the local directory path, or None if MinIO is unavailable.
    """
    from app.core.config import get_settings
    from app.core.database import get_minio_client

    try:
        settings = get_settings()
        minio = get_minio_client()
        bucket_name = bucket or settings.MINIO_BUCKET_DATASETS

        # Ensure the prefix has no leading slash for MinIO listing
        prefix = storage_path.lstrip("/")

        objects = list(minio.list_objects(bucket_name, prefix=prefix, recursive=True))
        files = [o for o in objects if not o.is_dir]
        if not files:
            logger.warning("No files found in MinIO at %s/%s", bucket_name, prefix)
            return None

        local_dir = tempfile.mkdtemp(prefix="fl_dataset_")
        for obj in files:
            # Preserve relative path structure under the local dir
            rel_path = obj.object_name
            if rel_path.startswith(prefix):
                rel_path = rel_path[len(prefix):]
            rel_path = rel_path.lstrip("/")

            local_path = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            minio.fget_object(bucket_name, obj.object_name, local_path)
            logger.debug("Downloaded %s -> %s", obj.object_name, local_path)

        logger.info("Downloaded %d files from MinIO to %s", len(files), local_dir)
        return local_dir
    except Exception as exc:
        logger.warning("Failed to download dataset from MinIO: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helper – resolve a dataset to a local JSONL path for training
# ---------------------------------------------------------------------------

def _resolve_dataset_path(ds, config) -> str | None:
    """Return a local file path for the dataset, downloading from MinIO if needed.

    Tries:
      1. Local filesystem (storage_path exists as-is)
      2. MinIO download to temp dir, then find the JSONL file

    Returns the path to a JSONL file, or None.
    """
    storage_path = ds.storage_path or ""

    # 1. Try local filesystem directly
    if os.path.exists(storage_path):
        if os.path.isfile(storage_path):
            return storage_path
        # It's a directory – look for a JSONL file inside
        for fname in os.listdir(storage_path):
            if fname.endswith(".jsonl"):
                return os.path.join(storage_path, fname)
        # If no JSONL, try any text file
        for fname in os.listdir(storage_path):
            if fname.endswith((".txt", ".json", ".csv")):
                return os.path.join(storage_path, fname)

    # 2. Try MinIO download
    local_dir = _download_dataset_from_minio(storage_path)
    if local_dir is not None:
        for fname in os.listdir(local_dir):
            if fname.endswith(".jsonl"):
                return os.path.join(local_dir, fname)
        # Try any text file
        for fname in os.listdir(local_dir):
            if fname.endswith((".txt", ".json", ".csv")):
                return os.path.join(local_dir, fname)
        # If directory has subdirectories, search deeper
        for root, _, files in os.walk(local_dir):
            for fname in files:
                if fname.endswith(".jsonl"):
                    return os.path.join(root, fname)

    return None


# ---------------------------------------------------------------------------
# Helper – build a training participant from a DB participant record
# ---------------------------------------------------------------------------

def _build_participant_from_db(
    p, config, provider, tokenizer, db, shared_memory,
):
    """Build a FederatedParticipant from a DB FederatedParticipant row.

    Args:
        p: DB FederatedParticipant row.
        config: FederatedConfig instance.
        provider: Model provider.
        tokenizer: Tokenizer instance.
        db: SQLAlchemy session.
        shared_memory: SharedMemoryManager for the coordinator.

    Returns:
        An llmt_training.federated.participant.FederatedParticipant instance.
    """
    from app.models.dataset import Dataset as DatasetModel
    from llmt_training.data.finetune_dataset import FinetuneDataset
    from llmt_training.federated.config import ParticipantConfig
    from llmt_training.federated.participant import FederatedParticipant

    p_config = ParticipantConfig(
        participant_id=p.participant_id,
        name=p.name,
        weight=p.weight,
        data_size=p.data_size,
        local_epochs=p.local_epochs,
        local_batch_size=p.local_batch_size,
        local_learning_rate=p.local_learning_rate,
        status=p.status,
        dataset_id=p.dataset_id,
    )

    # --- data loader ---
    train_dataloader: DataLoader | None = None
    if p.dataset_id is not None:
        ds = db.query(DatasetModel).filter(DatasetModel.id == p.dataset_id).first()
        if ds is not None:
            local_path = _resolve_dataset_path(ds, config)
            if local_path is not None:
                finetune_ds = FinetuneDataset.from_config({
                    "data": {"dataset_path": local_path},
                    "model": {"seq_length": config.seq_length},
                })
                if tokenizer is not None:
                    finetune_ds.tokenizer = tokenizer
                train_dataloader = DataLoader(
                    finetune_ds,
                    batch_size=p.local_batch_size,
                    shuffle=True,
                    num_workers=0,
                    drop_last=False,
                )
                logger.info(
                    "Participant %s: loaded dataset '%s' (%d samples) from %s",
                    p.participant_id, ds.name, len(finetune_ds), local_path,
                )
            else:
                logger.warning(
                    "Participant %s: dataset '%s' (id=%d) could not be resolved to a local file",
                    p.participant_id, ds.name, ds.id,
                )
        else:
            logger.warning(
                "Participant %s: dataset_id=%d not found in DB",
                p.participant_id, p.dataset_id,
            )

    if train_dataloader is None:
        logger.info(
            "Participant %s: no dataset available, using synthetic data",
            p.participant_id,
        )
        n_samples = max(p.data_size, 100)
        synthetic_samples = [
            {"text": f"federated training sample {i} for participant {p.participant_id}"}
            for i in range(n_samples)
        ]
        synth_ds = FinetuneDataset(
            samples=synthetic_samples,
            seq_length=config.seq_length,
            tokenizer=tokenizer,
        )
        train_dataloader = DataLoader(
            synth_ds,
            batch_size=p.local_batch_size,
            shuffle=True,
            num_workers=0,
            drop_last=False,
        )

    return FederatedParticipant(
        config=config,
        participant_config=p_config,
        model=provider.get_model(config.get_model_config_dict()),
        train_dataloader=train_dataloader,
        loss_fn=provider.get_loss_fn(config.get_model_config_dict()),
        shared_memory=shared_memory,
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=1)
def run_federated_task(self, task_code: str) -> dict:
    """Execute a federated learning training task via Celery.

    This task:
    1. Loads the federated config from DB
    2. Builds the global model
    3. Sets up participants with their data
    4. Runs the federated training loop
    5. Saves the final model

    Before each round the participant list is reloaded from DB so that
    dynamic add/remove calls take effect in the in-flight training run.

    Args:
        task_code: The federated task code to execute.

    Returns:
        Training result dict.
    """
    from app.core.database import SessionLocal
    from app.models.federated import FederatedTask, FederatedParticipant as DBParticipant

    db = SessionLocal()
    try:
        task = db.query(FederatedTask).filter(FederatedTask.task_code == task_code).first()
        if task is None:
            return {"status": "failed", "error": "Task not found"}

        task.status = "running"
        db.commit()

        # Import training framework
        from llmt_training.federated.config import FederatedConfig
        from llmt_training.federated.coordinator import FederatedCoordinator
        from llmt_training.models.registry import ModelRegistry

        # Build config
        config = FederatedConfig(**task.config_json)

        # Build global model & tokenizer
        provider = ModelRegistry.get(config.model_type)
        model = provider.get_model(config.get_model_config_dict())
        tokenizer = provider.get_tokenizer(config.get_model_config_dict())

        # Build coordinator
        coordinator = FederatedCoordinator(config=config, model=model)

        # Seed initial participants
        for p in task.participants:
            participant = _build_participant_from_db(
                p, config, provider, tokenizer, db, coordinator.shared_memory,
            )
            coordinator.register_participant(participant)

        # Initialize global model
        init_info = coordinator.initialize_global_model()

        # Verify minimum participants
        active_count = sum(
            1 for p in coordinator.participants.values()
            if p.participant_config.status == "active"
        )
        if active_count < config.min_participants:
            task.status = "failed"
            task.error_message = (
                f"Active participant count ({active_count}) below minimum "
                f"({config.min_participants})"
            )
            db.commit()
            return {"status": "failed", "error": task.error_message, "init_info": init_info}

        # -------------------------------------------------------------------
        # Explicit training loop with per-round participant sync from DB
        # -------------------------------------------------------------------
        coordinator._status = "running"
        training_start = time.time()
        round_results: list[dict[str, Any]] = []

        for round_num in range(1, config.num_rounds + 1):
            coordinator._current_round = round_num
            round_start = time.time()

            logger.info("=" * 60)
            logger.info("Starting Round %d/%d", round_num, config.num_rounds)
            logger.info("=" * 60)

            # ---- sync participants from DB ----
            db.refresh(task)

            # Check for cancellation
            if task.status == "cancelled":
                logger.info("Federated task %s cancelled at round %d", task_code, round_num)
                return {
                    "status": "cancelled",
                    "total_rounds": round_num - 1,
                }

            _sync_participants(coordinator, task, config, provider, tokenizer, db)

            # ---- distribute model ----
            coordinator.distribute_model()

            # ---- collect updates ----
            updates = coordinator.collect_updates()
            if not updates:
                logger.warning("No updates received in round %d, skipping", round_num)
                _persist_round_progress(db, task, coordinator, round_num)
                continue

            # ---- detect anomalies ----
            anomaly_report = coordinator.detect_and_handle_anomalies(updates)

            # Persist anomaly info to DB participants
            _persist_anomaly_info(db, task, anomaly_report)

            for pid in anomaly_report.get("anomalies", {}):
                if pid in updates:
                    del updates[pid]

            if not updates:
                logger.warning("All updates filtered as anomalous in round %d", round_num)
                _persist_round_progress(db, task, coordinator, round_num)
                continue

            # ---- aggregate ----
            coordinator.aggregate_updates(updates)

            # ---- compute metrics ----
            round_loss = coordinator._compute_round_loss()
            round_elapsed = round(time.time() - round_start, 2)

            round_info = {
                "round": round_num,
                "num_active_participants": len(updates),
                "round_loss": round_loss,
                "round_elapsed_seconds": round_elapsed,
                "anomaly_report": anomaly_report,
                "converged": False,
            }

            # ---- check convergence ----
            if coordinator.check_convergence(round_loss):
                round_info["converged"] = True
                round_results.append(round_info)
                break

            # ---- checkpoint ----
            if round_num % config.save_every_n_rounds == 0:
                coordinator.save_checkpoint(round_num)

            round_results.append(round_info)
            logger.info(
                "Round %d complete: loss=%.6f, participants=%d, elapsed=%.2fs",
                round_num, round_loss, len(updates), round_elapsed,
            )

            # Persist progress to DB after each round
            _persist_round_progress(db, task, coordinator, round_num)

        # ---- training complete ----
        total_elapsed = round(time.time() - training_start, 2)
        coordinator._status = "completed"

        # Save final model
        final_path = coordinator.save_checkpoint(coordinator._current_round, is_final=True)

        result = {
            "status": "completed",
            "init_info": init_info,
            "total_rounds": coordinator._current_round,
            "best_loss": round(coordinator._best_loss, 6),
            "total_elapsed_seconds": total_elapsed,
            "final_model_path": final_path,
            "round_results": round_results,
            "training_log": coordinator._training_log,
            "participant_statuses": {
                pid: p.get_status() for pid, p in coordinator.participants.items()
            },
        }

        logger.info(
            "Federated training complete: %s",
            {k: v for k, v in result.items() if k != "training_log"},
        )

        # ---- final DB update (don't overwrite cancelled) ----
        db.refresh(task)
        if task.status == "cancelled":
            logger.info("Federated task %s was cancelled, skipping final DB update", task_code)
            return {"status": "cancelled", "total_rounds": coordinator._current_round}

        task.status = result["status"]
        task.current_round = result.get("total_rounds", 0)
        task.best_loss = result.get("best_loss")
        task.final_model_path = result.get("final_model_path")
        task.result_json = result
        task.training_log_json = coordinator._training_log
        from datetime import datetime, timezone as tz
        task.ended_at = datetime.now(tz.utc)
        db.commit()
        return result

    except Exception as e:
        logger.exception("Federated task %s failed: %s", task_code, e)
        try:
            db.refresh(task)
            if task.status == "cancelled":
                logger.info("Federated task %s was cancelled, skipping error update", task_code)
                return {"status": "cancelled", "error": "Task was cancelled"}
            task.status = "failed"
            task.error_message = str(e)
            db.commit()
        except Exception:
            pass
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sync_participants(
    coordinator,
    task,
    config,
    provider,
    tokenizer,
    db,
) -> None:
    """Synchronise coordinator participants with the DB before a round.

    - Participants in DB but not in coordinator → build & register
    - Participants in coordinator but inactive/absent in DB → remove
    """
    from app.models.federated import FederatedParticipant as DBParticipant

    # Current DB participants for this task
    db_participants: dict[str, DBParticipant] = {
        p.participant_id: p
        for p in db.query(DBParticipant)
        .filter(DBParticipant.task_id == task.id)
        .all()
    }
    active_db_ids = {
        pid for pid, p in db_participants.items()
        if p.status == "active"
    }

    # Current coordinator participants
    coord_ids = set(coordinator.participants.keys())

    # ---- add new participants ----
    for pid in active_db_ids - coord_ids:
        p_row = db_participants[pid]
        participant = _build_participant_from_db(
            p_row, config, provider, tokenizer, db, coordinator.shared_memory,
        )
        coordinator.add_participant_dynamic(participant)

    # ---- remove participants no longer active in DB ----
    for pid in coord_ids - active_db_ids:
        coordinator.remove_participant_dynamic(pid)
        logger.info("Participant %s removed (no longer active in DB)", pid)


def _persist_anomaly_info(
    db, task, anomaly_report: dict[str, Any],
) -> None:
    """Write anomaly detection results back to DB participant rows."""
    if not anomaly_report or "anomalies" not in anomaly_report:
        return
    from app.models.federated import FederatedParticipant as DBParticipant

    anomalies: dict[str, dict] = anomaly_report["anomalies"]
    if not anomalies:
        return

    for pid, info in anomalies.items():
        db_p = (
            db.query(DBParticipant)
            .filter(DBParticipant.task_id == task.id, DBParticipant.participant_id == pid)
            .first()
        )
        if db_p is not None:
            db_p.anomaly_score = info.get("z_score")
            db_p.anomaly_details_json = info

    db.commit()


def _persist_round_progress(
    db, task, coordinator, round_num: int,
) -> None:
    """Write incremental progress back to DB after each round.

    Updates both the task row and each participant's runtime stats.
    """
    from app.models.federated import FederatedParticipant as DBParticipant

    task.current_round = round_num
    task.best_loss = (
        round(coordinator._best_loss, 6)
        if coordinator._best_loss != float("inf")
        else None
    )

    # Update participant runtime stats from coordinator state
    db_participants: dict[str, DBParticipant] = {
        p.participant_id: p
        for p in db.query(DBParticipant)
        .filter(DBParticipant.task_id == task.id)
        .all()
    }
    for pid, p_coord in coordinator.participants.items():
        db_p = db_participants.get(pid)
        if db_p is None:
            continue
        db_p.last_round_completed = round_num
        if p_coord._local_loss_history:
            db_p.last_loss = round(p_coord._local_loss_history[-1], 6)
        if p_coord.participant_config.status in ("malicious", "inactive"):
            db_p.status = p_coord.participant_config.status

    db.commit()

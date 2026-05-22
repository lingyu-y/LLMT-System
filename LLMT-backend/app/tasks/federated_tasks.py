"""Celery tasks for federated learning."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import torch
from torch.utils.data import DataLoader

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


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
    )

    # --- data loader ---
    train_dataloader: DataLoader | None = None
    if p.dataset_id is not None:
        ds = db.query(DatasetModel).filter(DatasetModel.id == p.dataset_id).first()
        if ds is not None and os.path.exists(ds.storage_path):
            finetune_ds = FinetuneDataset.from_config({
                "data": {"dataset_path": ds.storage_path},
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
                "Participant %s: loaded dataset '%s' (%d samples)",
                p.participant_id, ds.name, len(finetune_ds),
            )
        else:
            logger.warning(
                "Participant %s: dataset path '%s' does not exist",
                p.participant_id, ds.storage_path if ds else "(dataset not found)",
            )

    if train_dataloader is None:
        logger.info(
            "Participant %s: no dataset available, using synthetic data",
            p.participant_id,
        )
        from llmt_training.data.finetune_dataset import FinetuneDataset
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


def _persist_round_progress(
    db, task, coordinator, round_num: int,
) -> None:
    """Write incremental progress back to DB after each round."""
    task.current_round = round_num
    task.best_loss = (
        round(coordinator._best_loss, 6)
        if coordinator._best_loss != float("inf")
        else None
    )
    db.commit()

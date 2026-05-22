"""Celery tasks for federated learning."""

from __future__ import annotations

import logging

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1)
def run_federated_task(self, task_code: str) -> dict:
    """Execute a federated learning training task via Celery.

    This task:
    1. Loads the federated config from DB
    2. Builds the global model
    3. Sets up participants with their data
    4. Runs the federated training loop
    5. Saves the final model

    Args:
        task_code: The federated task code to execute.

    Returns:
        Training result dict.
    """
    from app.core.database import SessionLocal
    from app.models.federated import FederatedTask

    db = SessionLocal()
    try:
        task = db.query(FederatedTask).filter(FederatedTask.task_code == task_code).first()
        if task is None:
            return {"status": "failed", "error": "Task not found"}

        task.status = "running"
        db.commit()

        # Import training framework
        from llmt_training.federated.config import FederatedConfig, ParticipantConfig
        from llmt_training.federated.coordinator import FederatedCoordinator
        from llmt_training.federated.participant import FederatedParticipant
        from llmt_training.models.registry import ModelRegistry

        # Build config
        config = FederatedConfig(**task.config_json)

        # Build global model & tokenizer
        provider = ModelRegistry.get(config.model_type)
        model = provider.get_model(config.get_model_config_dict())
        tokenizer = provider.get_tokenizer(config.get_model_config_dict())

        # Build coordinator
        coordinator = FederatedCoordinator(config=config, model=model)

        # Load dataset for participants
        from app.models.dataset import Dataset as DatasetModel
        from llmt_training.data.finetune_dataset import FinetuneDataset
        from torch.utils.data import DataLoader

        # Add participants
        for p in task.participants:
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

            # Build data loader for this participant
            train_dataloader: DataLoader | None = None
            if p.dataset_id is not None:
                ds = db.query(DatasetModel).filter(DatasetModel.id == p.dataset_id).first()
                if ds is not None:
                    import os
                    storage_path = ds.storage_path
                    if os.path.exists(storage_path):
                        finetune_ds = FinetuneDataset.from_config({
                            "data": {"dataset_path": storage_path},
                            "model": {"seq_length": config.seq_length},
                        })
                        # If a tokenizer is available, attach it
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
                            p.participant_id, storage_path,
                        )

            if train_dataloader is None:
                logger.warning(
                    "Participant %s: no dataset available (dataset_id=%s), "
                    "will use synthetic data",
                    p.participant_id, p.dataset_id,
                )
                # Generate synthetic data so the participant can still train
                import torch
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

            participant = FederatedParticipant(
                config=config,
                participant_config=p_config,
                model=provider.get_model(config.get_model_config_dict()),
                train_dataloader=train_dataloader,
                loss_fn=provider.get_loss_fn(config.get_model_config_dict()),
                shared_memory=coordinator.shared_memory,
            )
            coordinator.register_participant(participant)

        # Run training
        result = coordinator.train()

        # Update DB
        task.status = result["status"]
        task.current_round = result.get("total_rounds", 0)
        task.best_loss = result.get("best_loss")
        task.final_model_path = result.get("final_model_path")
        task.result_json = result
        task.training_log_json = coordinator._training_log

        if result["status"] == "completed":
            from datetime import datetime, timezone
            task.ended_at = datetime.now(timezone.utc)

        db.commit()
        return result

    except Exception as e:
        logger.exception("Federated task %s failed: %s", task_code, e)
        try:
            task = db.query(FederatedTask).filter(FederatedTask.task_code == task_code).first()
            if task:
                task.status = "failed"
                task.error_message = str(e)
                db.commit()
        except Exception:
            pass
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()

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
        from llmt_training.federated.config import FederatedConfig
        from llmt_training.federated.coordinator import FederatedCoordinator
        from llmt_training.federated.participant import FederatedParticipant
        from llmt_training.models.registry import get_model_provider

        # Build config
        config = FederatedConfig(**task.config_json)

        # Build global model
        provider = get_model_provider(config.model_type)
        model = provider.get_model(config.get_model_config_dict())

        # Build coordinator
        coordinator = FederatedCoordinator(config=config, model=model)

        # Add participants
        for p in task.participants:
            p_config = config.participants[0].__class__(
                participant_id=p.participant_id,
                name=p.name,
                weight=p.weight,
                data_size=p.data_size,
                local_epochs=p.local_epochs,
                local_batch_size=p.local_batch_size,
                local_learning_rate=p.local_learning_rate,
                status=p.status,
            )
            participant = FederatedParticipant(
                config=config,
                participant_config=p_config,
                model=provider.get_model(config.get_model_config_dict()),
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

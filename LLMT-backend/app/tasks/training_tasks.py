"""Celery training tasks – async execution of training jobs."""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

from app.core.celery_app import celery_app
from app.core.config import get_settings

settings = get_settings()


@celery_app.task(
    name="run_training_task",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def run_training_task(self, task_code: str) -> dict[str, Any]:
    """Execute a training task via the LLMT-Training framework.

    This is the main Celery task that:
    1. Loads the TrainingTask config from PostgreSQL
    2. Validates the config
    3. Creates a Trainer + Launcher
    4. Executes the training
    5. Reports results back

    Args:
        task_code: The unique task code from TrainingTask.task_code

    Returns:
        A dict with task_code, status, and optional error_message.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.training_task import TrainingTask
    from app.services.training_service import validate_config

    # --- 1. Load config from DB ---
    engine = create_engine(settings.postgres_database_url)
    with Session(engine) as db:
        task = db.query(TrainingTask).filter(TrainingTask.task_code == task_code).first()
        if task is None:
            return {"task_code": task_code, "status": "failed", "error_message": "Task not found"}

        config_json = task.config_json
        framework = task.framework or "deepspeed"
        parallel_strategy = task.parallel_strategy or "zero2"

    # --- 2. Build full training config ---
    from llmt_training.config.schema import TrainingConfig

    try:
        # Merge backend config_json into TrainingConfig structure
        training_config = _build_training_config(
            task_code=task_code,
            framework=framework,
            parallel_strategy=parallel_strategy,
            config_json=config_json,
        )
    except Exception as e:
        _update_task_status(task_code, "failed", error_message=f"Config error: {e}")
        return {"task_code": task_code, "status": "failed", "error_message": str(e)}

    # --- 3. Validate config ---
    validation = ConfigValidator_safe_validate(training_config)
    if not validation.get("valid", True):
        errors = validation.get("errors", [])
        _update_task_status(task_code, "failed", error_message=f"Validation: {'; '.join(errors)}")
        return {"task_code": task_code, "status": "failed", "error_message": "; ".join(errors)}

    # --- 4. Execute training ---
    _update_task_status(task_code, "running")

    try:
        config_dict = training_config if isinstance(training_config, dict) else training_config

        # Build reporting callback
        from llmt_training.reporting.callback_bridge import ReportingCallbackBridge
        reporting_callback = ReportingCallbackBridge.from_config(config_dict)

        # Create trainer
        from llmt_training.trainers.factory import create_trainer
        from llmt_training.core.callbacks import CallbackList
        from llmt_training.core.state import TrainingState

        state = TrainingState(
            task_code=task_code,
            max_epochs=config_dict.get("hyperparams", {}).get("max_epochs", 10),
            max_steps=config_dict.get("hyperparams", {}).get("max_steps"),
        )
        callbacks = CallbackList([reporting_callback])

        trainer = create_trainer(
            framework=framework,
            parallel_strategy=parallel_strategy,
            config=config_dict,
            callbacks=callbacks,
            state=state,
        )

        # For in-process training (pytorch/deepspeed single-node)
        if framework in ("pytorch", "deepspeed") and _should_run_in_process(config_dict):
            final_state = trainer.train()
        else:
            # For distributed/megatron: use launcher
            from llmt_training.launcher.factory import create_launcher
            launcher = create_launcher(framework, parallel_strategy, config_dict)

            # Write config to temp file for the subprocess
            config_path = os.path.join(
                config_dict.get("checkpoint", {}).get("checkpoint_dir", "./checkpoints"),
                "training_config.json",
            )
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(config_dict, f, indent=2)

            # Build trainer script path
            trainer_script = _get_trainer_script(framework)
            exit_code = launcher.launch(
                trainer_script,
                config_json=json.dumps(config_dict),
            )

            if exit_code == 0:
                final_state = state
                final_state.status = "completed"
            else:
                final_state = state
                final_state.status = "failed"
                final_state.error_message = f"Training process exited with code {exit_code}"

        return {
            "task_code": task_code,
            "status": final_state.status,
            "error_message": final_state.error_message,
        }

    except Exception as e:
        _update_task_status(task_code, "failed", error_message=str(e))
        return {"task_code": task_code, "status": "failed", "error_message": str(e)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_training_config(
    task_code: str,
    framework: str,
    parallel_strategy: str,
    config_json: dict,
) -> dict[str, Any]:
    """Build a full training config dict from the backend's config_json."""
    # The backend's config_json may be flat (from TrainingConfigDict)
    # We need to restructure it into the nested TrainingConfig format
    config: dict[str, Any] = {
        "task_code": task_code,
        "framework": framework,
        "parallel_strategy": parallel_strategy,
        "model": {},
        "data": {},
        "hyperparams": {},
        "strategy": {},
        "checkpoint": {},
        "reporting": {
            "influxdb_url": settings.INFLUXDB_URL,
            "influxdb_token": settings.INFLUXDB_TOKEN,
            "influxdb_org": settings.INFLUXDB_ORG,
            "influxdb_bucket": settings.INFLUXDB_BUCKET,
        },
    }

    # Map flat keys to nested structure
    model_keys = {
        "model_type", "vocab_size", "hidden_size", "num_layers",
        "num_attention_heads", "intermediate_size", "seq_length",
        "max_position_embeddings", "dropout", "layer_norm_eps", "activation",
    }
    data_keys = {
        "dataset_path", "dataset_format", "train_split", "seed", "num_workers", "pin_memory",
    }
    hyperparam_keys = {
        "batch_size", "learning_rate", "min_lr", "weight_decay", "max_epochs",
        "max_steps", "warmup_steps", "max_grad_norm", "gradient_accumulation_steps",
        "optimizer", "scheduler", "precision", "beta1", "beta2", "adam_epsilon", "lr_decay_iters",
    }
    strategy_keys = {
        "num_gpus", "num_nodes", "tensor_model_parallel_size",
        "pipeline_model_parallel_size", "zero_stage", "zero_offload",
    }
    checkpoint_keys = {
        "save_interval", "eval_interval", "max_checkpoints", "upload_to_minio",
    }

    for key, value in config_json.items():
        if key in model_keys:
            config["model"][key] = value
        elif key in data_keys:
            config["data"][key] = value
        elif key in hyperparam_keys:
            config["hyperparams"][key] = value
        elif key in strategy_keys:
            config["strategy"][key] = value
        elif key in checkpoint_keys:
            config["checkpoint"][key] = value
        elif key == "deepspeed_overrides":
            config["deepspeed_overrides"] = value
        elif key == "megatron_overrides":
            config["megatron_overrides"] = value

    return config


def _update_task_status(
    task_code: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update TrainingTask status in PostgreSQL."""
    try:
        from llmt_training.reporting.postgres_status import PostgresStatusUpdater
        updater = PostgresStatusUpdater(db_url=settings.postgres_database_url)
        updater.update_progress(
            task_code, status=status, error_message=error_message,
        )
    except Exception:
        pass  # Best-effort status update


def ConfigValidator_safe_validate(config: dict) -> dict:
    """Validate config safely, returning a dict result."""
    try:
        from llmt_training.config.schema import TrainingConfig
        from llmt_training.config.validator import ConfigValidator
        tc = TrainingConfig(**config)
        result = ConfigValidator.validate(tc)
        return {"valid": result.valid, "errors": result.errors, "warnings": result.warnings}
    except Exception as e:
        return {"valid": False, "errors": [str(e)], "warnings": []}


def _should_run_in_process(config: dict) -> bool:
    """Decide whether to run training in-process vs. subprocess launcher."""
    strategy = config.get("strategy", {})
    num_gpus = strategy.get("num_gpus", 1)
    num_nodes = strategy.get("num_nodes", 1)
    # Single-GPU, single-node: run in-process for simplicity
    return num_gpus <= 1 and num_nodes <= 1


def _get_trainer_script(framework: str) -> str:
    """Get the path to the appropriate trainer entry script."""
    module_path = settings.LLMT_TRAINING_MODULE_PATH
    # Look for example scripts
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    scripts_dir = os.path.join(base, "LLMT-training", "examples")

    if framework == "megatron":
        return os.path.join(scripts_dir, "gpt_pretrain.py")
    else:
        return os.path.join(scripts_dir, "gpt_pretrain.py")

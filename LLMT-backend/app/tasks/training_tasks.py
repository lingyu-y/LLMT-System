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


def _ensure_llmt_training_on_path() -> None:
    """Register the llmt_training package even if pip install -e . wasn't run.

    The repo directory is ``LLMT-training/`` (hyphen) but the Python package
    is ``llmt_training`` (underscore).  Simply adding the repo root to
    ``sys.path`` won't work because Python can't import a directory whose
    name contains a hyphen.  Instead we use ``importlib.util`` to load the
    ``__init__.py`` and register the module explicitly.
    """
    try:
        import llmt_training  # noqa: F401
        return
    except ImportError:
        pass

    # Resolve the physical path to the LLMT-training source directory
    module_path = settings.LLMT_TRAINING_MODULE_PATH
    if os.path.isdir(module_path):
        source_dir = module_path
    else:
        # Derive from repo layout: LLMT-training is a sibling of LLMT-backend
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

    # Register llmt_training as a package pointing to source_dir
    import importlib.util
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

        # Resolve dataset_path from dataset_id if not already set
        if not config_json.get("dataset_path") and task.dataset_id:
            from app.models.dataset import Dataset
            dataset = db.query(Dataset).filter(Dataset.id == task.dataset_id).first()
            if dataset:
                local_path = _resolve_dataset_path(dataset)
                if local_path:
                    config_json["dataset_path"] = local_path
                else:
                    config_json["dataset_path"] = dataset.storage_path
                config_json["dataset_format"] = config_json.get("dataset_format") or dataset.data_type

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

        # Build model from config via ModelRegistry
        from llmt_training.models.registry import ModelRegistry
        model_type = config_dict.get("model", {}).get("model_type", "gpt2")
        model_provider = ModelRegistry.get(model_type)
        model = model_provider.get_model(config_dict.get("model", {}))

        # Build dataloaders from config
        from llmt_training.data.data_utils import create_dataset_from_config, build_dataloaders
        is_distributed = config_dict.get("strategy", {}).get("num_gpus", 1) > 1
        dataset = create_dataset_from_config(config_dict)
        train_dataloader, eval_dataloader = build_dataloaders(
            dataset, config_dict, distributed=is_distributed,
        )

        # Build loss function from model provider
        loss_fn = model_provider.get_loss_fn(config_dict.get("model", {}))

        # Create trainer
        from llmt_training.trainers.factory import create_trainer
        from llmt_training.core.callbacks import CallbackList
        from llmt_training.core.state import TrainingState

        state = TrainingState(
            task_code=task_code,
            max_epochs=config_dict.get("hyperparams", {}).get("max_epochs", 10),
            max_steps=config_dict.get("hyperparams", {}).get("max_steps"),
        )
        callbacks = CallbackList([reporting_callback, _CancellationCheckCallback(task_code)])

        trainer = create_trainer(
            framework=framework,
            parallel_strategy=parallel_strategy,
            config=config_dict,
            model=model,
            train_dataloader=train_dataloader,
            eval_dataloader=eval_dataloader,
            callbacks=callbacks,
            state=state,
            loss_fn=loss_fn,
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

class _CancellationCheckCallback:
    """Callback that polls the DB for cancellation status.

    Celery ``revoke(..., terminate=True)`` only sends SIGTERM to the worker
    process, which may be ignored or arrive late.  This callback provides
    cooperative cancellation: on every ``on_step_end`` it queries PostgreSQL
    for the current task status and, if the row has been marked
    ``cancelled``, propagates that into ``state.status`` so the trainer's
    ``_should_stop()`` check will exit the loop cleanly.
    """

    def __init__(self, task_code: str, poll_every: int = 10):
        self._task_code = task_code
        self._poll_every = poll_every  # check DB every N steps
        self._step_counter = 0

    # -- TrainingCallback interface ------------------------------------------

    def on_train_begin(self, state, **kwargs):
        pass

    def on_train_end(self, state, **kwargs):
        pass

    def on_epoch_begin(self, state, **kwargs):
        pass

    def on_epoch_end(self, state, **kwargs):
        pass

    def on_step_end(self, state, **kwargs):
        self._step_counter += 1
        if self._step_counter % self._poll_every != 0:
            return
        try:
            from sqlalchemy import create_engine as _ce
            from sqlalchemy.orm import Session as _S
            from app.models.training_task import TrainingTask as _TT
            _engine = _ce(settings.postgres_database_url)
            with _S(_engine) as db:
                row = db.query(_TT).filter(_TT.task_code == self._task_code).first()
                if row is not None and row.status == "cancelled":
                    state.status = "cancelled"
        except Exception:
            pass  # best-effort; don't crash training on a DB hiccup

    def on_checkpoint(self, state, **kwargs):
        pass

    def on_error(self, state, **kwargs):
        pass


def _resolve_dataset_path(ds) -> str | None:
    """Return a local file path for the dataset, downloading from MinIO if needed.

    Tries:
      1. Local filesystem (storage_path exists as-is)
      2. MinIO download to temp dir, then find the data file

    Returns the path to a data file, or None.
    """
    import logging
    logger = logging.getLogger(__name__)
    storage_path = ds.storage_path or ""

    # 1. Try local filesystem directly
    if os.path.exists(storage_path):
        if os.path.isfile(storage_path):
            return storage_path
        # It's a directory – look for a data file inside
        for fname in os.listdir(storage_path):
            if fname.endswith((".jsonl", ".npy", ".bin", ".txt", ".json", ".csv")):
                return os.path.join(storage_path, fname)
        # If directory has subdirectories, search deeper
        for root, _, files in os.walk(storage_path):
            for fname in files:
                if fname.endswith((".jsonl", ".npy", ".bin", ".txt", ".json", ".csv")):
                    return os.path.join(root, fname)

    # 2. Try MinIO download
    local_dir = _download_dataset_from_minio(storage_path)
    if local_dir is not None:
        for fname in os.listdir(local_dir):
            if fname.endswith((".jsonl", ".npy", ".bin", ".txt", ".json", ".csv")):
                return os.path.join(local_dir, fname)
        for root, _, files in os.walk(local_dir):
            for fname in files:
                if fname.endswith((".jsonl", ".npy", ".bin", ".txt", ".json", ".csv")):
                    return os.path.join(root, fname)

    return None


def _download_dataset_from_minio(
    storage_path: str,
    bucket: str | None = None,
) -> str | None:
    """Download all files under *storage_path* from MinIO to a local temp dir.

    Returns the local directory path, or None if MinIO is unavailable.
    """
    import logging
    import tempfile
    logger = logging.getLogger(__name__)

    try:
        from app.core.database import get_minio_client

        minio = get_minio_client()
        bucket_name = bucket or settings.MINIO_BUCKET_DATASETS

        # Ensure the prefix has no leading slash for MinIO listing
        prefix = storage_path.lstrip("/")

        objects = list(minio.list_objects(bucket_name, prefix=prefix, recursive=True))
        files = [o for o in objects if not o.is_dir]
        if not files:
            logger.warning("No files found in MinIO at %s/%s", bucket_name, prefix)
            return None

        local_dir = tempfile.mkdtemp(prefix="train_dataset_")
        for obj in files:
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
        if value is None:
            continue  # skip None values so Pydantic defaults are used
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
    """Update TrainingTask status in PostgreSQL directly via SQLAlchemy."""
    try:
        from sqlalchemy import create_engine as _ce, update as _upd
        from sqlalchemy.orm import Session as _S
        from app.models.training_task import TrainingTask as _TT
        from datetime import datetime as _dt, timezone as _tz
        _engine = _ce(settings.postgres_database_url)
        with _S(_engine) as db:
            values: dict[str, Any] = {"status": status}
            if error_message is not None:
                values["error_message"] = error_message
            if status in ("completed", "failed", "cancelled"):
                values["ended_at"] = _dt.now(_tz.utc)
            db.execute(_upd(_TT).where(_TT.task_code == task_code).values(**values))
            db.commit()
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
    """Get the path to the appropriate trainer entry script.

    Resolution order:
      1. ``LLMT_TRAINING_SCRIPTS_DIR`` env-var / settings key (absolute path)
      2. ``LLMT_TRAINING_MODULE_PATH`` if it points to an existing directory
      3. Relative path derived from this file's location:
         ``__file__`` is ``<repo>/LLMT-backend/app/tasks/training_tasks.py``
         so 4 levels up → ``<repo>/``, then ``LLMT-training/examples/``
    """
    # 1. Explicit override via settings / env
    scripts_dir = getattr(settings, "LLMT_TRAINING_SCRIPTS_DIR", None)
    if scripts_dir and os.path.isdir(scripts_dir):
        script = os.path.join(scripts_dir, _script_name(framework))
        if os.path.isfile(script):
            return script

    # 2. LLMT_TRAINING_MODULE_PATH as filesystem path
    module_path = settings.LLMT_TRAINING_MODULE_PATH
    candidate = os.path.join(module_path, "examples")
    if os.path.isdir(candidate):
        script = os.path.join(candidate, _script_name(framework))
        if os.path.isfile(script):
            return script

    # 3. Derive from repo layout: LLMT-training is a sibling of LLMT-backend
    #    __file__ = <repo>/LLMT-backend/app/tasks/training_tasks.py
    #    4 dirname hops → <repo>/
    repo_root = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    )
    scripts_dir = os.path.join(repo_root, "LLMT-training", "examples")
    return os.path.join(scripts_dir, _script_name(framework))


def _script_name(framework: str) -> str:
    """Return the entry-point script filename for *framework*."""
    # Currently all strategies use gpt_pretrain.py; extend as needed.
    return "gpt_pretrain.py"

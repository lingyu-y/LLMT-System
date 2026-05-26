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

    **Critical**: We also create a symlink ``llmt_training -> LLMT-training``
    in the same parent directory and add that parent to both ``sys.path`` and
    ``PYTHONPATH`` so that DataLoader worker sub-processes (spawned via
    ``multiprocessing``) can also find the package.
    """
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

    # Create a symlink so multiprocessing workers can also find the package.
    # LLMT-training/ (hyphen) -> llmt_training/ (underscore) symlink
    parent_dir = os.path.dirname(source_dir)
    symlink_path = os.path.join(parent_dir, "llmt_training")
    if os.path.islink(symlink_path) and os.path.realpath(symlink_path) != os.path.realpath(source_dir):
        try:
            os.unlink(symlink_path)
        except OSError:
            pass
    if not os.path.exists(symlink_path):
        try:
            os.symlink(source_dir, symlink_path)
        except OSError:
            pass  # Permission or FS issue; num_workers=0 will be the fallback

    # Add parent directory to sys.path and PYTHONPATH for child processes
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    existing_pp = os.environ.get("PYTHONPATH", "")
    if parent_dir not in existing_pp:
        os.environ["PYTHONPATH"] = f"{parent_dir}:{existing_pp}" if existing_pp else parent_dir

    # Register llmt_training as a package pointing to source_dir for this process.
    try:
        import llmt_training  # noqa: F401
        return
    except ImportError:
        pass

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

        # Defensive fix: if user selected PyTorch but left a ZeRO parallel
        # strategy (zero1/zero2/zero3), switch to 'ddp' automatically and
        # append a warning to the task so the user sees the correction.
        if framework == "pytorch" and (parallel_strategy or "").startswith("zero"):
            from datetime import datetime
            old = parallel_strategy
            parallel_strategy = "ddp"
            try:
                db.execute(
                    "UPDATE training_tasks SET status = :status, error_message = :msg, updated_at = :now WHERE task_code = :code",
                    {
                        "status": task.status,
                        "msg": f"警告：并行策略 {old} 与 PyTorch 不兼容，已自动切换为 'ddp'。",
                        "now": datetime.utcnow(),
                        "code": task_code,
                    },
                )
                db.commit()
            except Exception:
                pass

        # Resolve dataset_path from dataset_id if not already set
        if not config_json.get("dataset_path") and task.dataset_id:
            from app.models.dataset import Dataset
            dataset = db.query(Dataset).filter(Dataset.id == task.dataset_id).first()
            if dataset:
                local_paths = _resolve_dataset_paths(dataset)
                if local_paths:
                    # Set primary path + all paths for multi-file streaming
                    config_json["dataset_path"] = local_paths[0]
                    if len(local_paths) > 1:
                        config_json["dataset_paths"] = local_paths
                    import logging
                    _log = logging.getLogger(__name__)
                    _log.info("训练任务 %s 数据集 '%s' 解析到 %d 个文件:", task_code, dataset.name, len(local_paths))
                    for i, p in enumerate(local_paths):
                        _log.info("  [%d/%d] %s", i + 1, len(local_paths), p)
                else:
                    _update_task_status(
                        task_code, "failed",
                        error_message=(
                            f"数据集文件无法访问：storage_path='{dataset.storage_path}'。"
                            "文件在本地不存在且无法从 MinIO 下载，请确认数据已正确上传。"
                        ),
                    )
                    return {"task_code": task_code, "status": "failed",
                            "error_message": f"数据集文件无法访问：{dataset.storage_path}"}
                # Map data_type (text/doc/excel) → training format (jsonl/npy/bin)
                if config_json.get("dataset_format"):
                    fmt = config_json["dataset_format"]
                else:
                    fmt = _map_data_type_to_format(
                        dataset.data_type, local_paths[0] if local_paths else "",
                    )
                config_json["dataset_format"] = fmt

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

        # --- Reload training modules so code changes take effect without ---
        # --- restarting the Celery worker (in-process path caches imports) ---
        import importlib
        import llmt_training.data.finetune_dataset as _fdm
        import llmt_training.data.pretrain_dataset as _pdm
        import llmt_training.data.data_utils as _dum
        import llmt_training.trainers.deepspeed_trainer as _dsm
        import llmt_training.trainers.pytorch_trainer as _ptm
        import llmt_training.trainers.factory as _tf
        importlib.reload(_fdm)
        importlib.reload(_pdm)
        importlib.reload(_dum)
        importlib.reload(_dsm)
        importlib.reload(_ptm)
        importlib.reload(_tf)

        # Build model from config via ModelRegistry
        from llmt_training.models.registry import ModelRegistry
        model_type = config_dict.get("model", {}).get("model_type", "gpt2")
        model_provider = ModelRegistry.get(model_type)
        model = model_provider.get_model(config_dict.get("model", {}))

        # --- Fine-tune: load pretrained weights from a previous ModelVersion ---
        base_model_version_id = config_dict.get("base_model_version_id")
        if base_model_version_id is not None:
            _load_pretrained_weights(model, base_model_version_id)

        # Build dataloaders from config
        from llmt_training.data.data_utils import create_dataset_from_config, build_dataloaders
        is_distributed = config_dict.get("strategy", {}).get("num_gpus", 1) > 1
        dataset = create_dataset_from_config(config_dict)
        _prepopulate_tokenizer_vocab(dataset)
        train_dataloader, eval_dataloader = build_dataloaders(
            dataset, config_dict, distributed=is_distributed,
        )
        print(
            f"[TrainingTask] dataloaders ready: train_batches={len(train_dataloader)}, "
            f"eval_batches={len(eval_dataloader) if eval_dataloader is not None else 0}",
            flush=True,
        )

        # Compute and store total training steps for progress bar
        steps_per_epoch = len(train_dataloader)
        max_steps_cfg = config_dict.get("hyperparams", {}).get("max_steps")
        max_epochs_cfg = config_dict.get("hyperparams", {}).get("max_epochs", 10)
        total_steps = max_steps_cfg if (max_steps_cfg and max_steps_cfg > 0) else max_epochs_cfg * steps_per_epoch
        _store_total_steps(task_code, total_steps, steps_per_epoch)
        print(
            f"[TrainingTask] total_steps={total_steps} (steps_per_epoch={steps_per_epoch}, "
            f"max_epochs={max_epochs_cfg}, max_steps={max_steps_cfg})",
            flush=True,
        )

        # Build loss function from model provider
        loss_fn = model_provider.get_loss_fn(config_dict.get("model", {}))

        # Create trainer
        from llmt_training.trainers.factory import create_trainer
        from llmt_training.core.callbacks import CallbackList
        from llmt_training.core.state import TrainingState

        # Detect resume: if task has previous progress, restore state
        resume_epoch = task.current_epoch
        resume_step = task.current_step
        resume_ckpt = task.checkpoint_path

        state = TrainingState(
            task_code=task_code,
            max_epochs=config_dict.get("hyperparams", {}).get("max_epochs", 10),
            max_steps=config_dict.get("hyperparams", {}).get("max_steps"),
        )
        if resume_step > 0:
            state.epoch = resume_epoch
            state.global_step = resume_step
        cancel_cb = _CancellationCheckCallback(task_code)
        callbacks = CallbackList([reporting_callback, cancel_cb])

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
        print(
            f"[TrainingTask] trainer ready: framework={framework}, "
            f"strategy={parallel_strategy}, starting training...",
            flush=True,
        )

        cancel_cb.set_trainer(trainer)

        # On resume, load the last checkpoint so training continues from there.
        if resume_step > 0:
            ckpt_candidates = [
                resume_ckpt,
                # New format: ckpt/ subdirectory (matching DeepSpeed structure)
                "/tmp/llmt_checkpoints/ckpt",
                "/tmp/llmt_checkpoints/ckpt/checkpoint.pt",
                # Old format: single .pt file
                "/tmp/llmt_checkpoints/checkpoint.pt",
                "./checkpoints/ckpt",
                "./checkpoints/ckpt/checkpoint.pt",
                "./checkpoints/checkpoint.pt",
            ]
            for ckpt in ckpt_candidates:
                if ckpt and os.path.exists(ckpt):
                    try:
                        trainer.load_checkpoint(ckpt)
                        print(f"[TrainingTask] resumed from checkpoint {ckpt}", flush=True)
                        break
                    except Exception:
                        pass

        # For in-process training (pytorch/deepspeed single-node)
        if framework in ("pytorch", "deepspeed") and _should_run_in_process(config_dict):
            final_state = trainer.train()
        else:
            # For distributed/megatron: use launcher
            from llmt_training.launcher.factory import create_launcher
            launcher = create_launcher(framework, parallel_strategy, config_dict)

            # Write config to temp file for the subprocess
            config_path = os.path.join(
                config_dict.get("checkpoint", {}).get("checkpoint_dir", "/tmp/llmt_checkpoints"),
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

        # Save tokenizer vocab alongside checkpoint for inference
        _save_tokenizer_vocab(dataset, config_dict)
        if final_state.status == "completed":
            _promote_to_model(task_code)

        # Explicitly update DB status so completion is reflected even if the
        # callback bridge's PostgreSQL updater is unavailable.
        _update_task_status(
            task_code,
            status=final_state.status,
            error_message=final_state.error_message,
        )

        return {
            "task_code": task_code,
            "status": final_state.status,
            "error_message": final_state.error_message,
        }

    except Exception as e:
        _update_task_status(task_code, "failed", error_message=str(e))
        return {"task_code": task_code, "status": "failed", "error_message": str(e)}


def _save_tokenizer_vocab(dataset, config_dict: dict) -> None:
    """Save tokenizer artifacts alongside the checkpoint for inference.

    SimpleTokenizer writes tokenizer_vocab.json. HuggingFace tokenizers write
    a tokenizer/ directory via save_pretrained().
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        tokenizer = getattr(dataset, "tokenizer", None)
        if tokenizer is None:
            if hasattr(dataset, "_loaded_samples") and hasattr(dataset, "tokenizer"):
                tokenizer = dataset.tokenizer
        can_save_simple = hasattr(tokenizer, "save_vocab")
        can_save_pretrained = hasattr(tokenizer, "save_pretrained")
        if tokenizer is None or not (can_save_simple or can_save_pretrained):
            logger.debug("No saveable tokenizer found on dataset, skipping vocab save")
            return

        # Create known local targets instead of writing only when they already
        # exist; otherwise short runs or different launchers can finish without
        # a tokenizer artifact.
        ckpt_dir_cfg = config_dict.get("checkpoint", {}).get("checkpoint_dir", "/tmp/llmt_checkpoints")
        ckpt_root = os.path.join(ckpt_dir_cfg) if not os.path.isabs(ckpt_dir_cfg) else ckpt_dir_cfg

        candidates = [
            ckpt_root,
            os.path.join(ckpt_root, "ckpt"),
            "./checkpoints",
            "./checkpoints/ckpt",
        ]
        written: set[str] = set()
        for base in candidates:
            os.makedirs(base, exist_ok=True)
            if can_save_simple:
                vocab_path = os.path.join(base, "tokenizer_vocab.json")
                if vocab_path not in written:
                    tokenizer.save_vocab(vocab_path)
                    written.add(vocab_path)
                    logger.info("Saved tokenizer vocab (%d words) to %s", len(tokenizer.id_to_word), vocab_path)
            if can_save_pretrained:
                tokenizer_dir = os.path.join(base, "tokenizer")
                if tokenizer_dir not in written:
                    os.makedirs(tokenizer_dir, exist_ok=True)
                    tokenizer.save_pretrained(tokenizer_dir)
                    written.add(tokenizer_dir)
                    logger.info("Saved tokenizer files to %s", tokenizer_dir)

        # DeepSpeed convention: latest is a file containing the current tag.
        for base in (ckpt_root, "./checkpoints"):
            latest_file = os.path.join(base, "latest")
            if os.path.isfile(latest_file):
                with open(latest_file, "r") as f:
                    latest_dir = f.read().strip()
                step_dir = os.path.join(base, latest_dir)
                if os.path.isdir(step_dir) and can_save_simple:
                    vocab_path = os.path.join(step_dir, "tokenizer_vocab.json")
                    if vocab_path not in written:
                        tokenizer.save_vocab(vocab_path)
                        written.add(vocab_path)
                        logger.info("Saved tokenizer vocab (%d words) to %s", len(tokenizer.id_to_word), vocab_path)
                if os.path.isdir(step_dir) and can_save_pretrained:
                    tokenizer_dir = os.path.join(step_dir, "tokenizer")
                    if tokenizer_dir not in written:
                        os.makedirs(tokenizer_dir, exist_ok=True)
                        tokenizer.save_pretrained(tokenizer_dir)
                        written.add(tokenizer_dir)
                        logger.info("Saved tokenizer files to %s", tokenizer_dir)
    except Exception as exc:
        logger.warning("Failed to save tokenizer vocab: %s", exc)


def _prepopulate_tokenizer_vocab(dataset) -> None:
    """Pre-populate the tokenizer's vocab from all dataset texts BEFORE training.

    This ensures the reverse vocabulary is fully built regardless of whether
    DataLoader uses worker subprocesses or launcher spawns a child process.
    """
    try:
        tokenizer = getattr(dataset, "tokenizer", None)
        if tokenizer is None or not hasattr(tokenizer, "build_vocab_from_texts"):
            return

        texts: list[str] = []
        # FinetuneDataset stores samples in self.samples
        if hasattr(dataset, "samples"):
            for s in dataset.samples:
                t = s.get("text", "") if isinstance(s, dict) else str(s)
                if t:
                    texts.append(t)
        # ShardedFinetuneDataset has per-shard samples
        elif hasattr(dataset, "file_paths"):
            for path in dataset.file_paths:
                try:
                    from llmt_training.data.finetune_dataset import _parse_file_samples
                    for s in _parse_file_samples(path):
                        t = s.get("text", "") if isinstance(s, dict) else str(s)
                        if t:
                            texts.append(t)
                except Exception:
                    pass

        if texts:
            tokenizer.build_vocab_from_texts(texts)
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Pre-populated tokenizer vocab with %d words from %d texts",
                        len(tokenizer.id_to_word), len(texts))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CancellationCheckCallback:
    """Callback that polls the DB for cancellation / pause / pausing status.

    On ``cancelled`` — propagates to ``state.status`` so the trainer's
    ``_should_stop()`` exits the loop cleanly.

    On ``pausing`` — saves a checkpoint, then transitions status to
    ``paused`` so the frontend sees the true paused state.
    """

    def __init__(self, task_code: str, poll_every: int = 10):
        self._task_code = task_code
        self._poll_every = poll_every
        self._step_counter = 0
        self._trainer_ref = None  # set by caller so we can trigger checkpoint

    def set_trainer(self, trainer):
        self._trainer_ref = trainer

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
                if row is None:
                    # DB record was deleted — stop training
                    state.status = "cancelled"
                    return
                if row.status == "cancelled":
                    state.status = "cancelled"
                elif row.status == "pausing":
                    # Save checkpoint so we can resume from here, then mark paused
                    if self._trainer_ref is not None:
                        try:
                            ckpt_dir = "/tmp/llmt_checkpoints"
                            self._trainer_ref.save_checkpoint(ckpt_dir)
                        except Exception:
                            pass
                    # Transition DB from 'pausing' → 'paused' atomically
                    try:
                        row.status = "paused"
                        db.commit()
                    except Exception:
                        pass
                    state.status = "paused"
        except Exception:
            pass

    def on_checkpoint(self, state, **kwargs):
        pass

    def on_error(self, state, **kwargs):
        pass


def _map_data_type_to_format(data_type: str, file_path: str) -> str:
    """Map dataset.data_type (text/doc/excel/other) to training framework format.

    The training framework expects: jsonl, parquet, npy, bin, megatron_bin_idx.
    The backend stores data_type as: text, doc, excel, other.

    We also check the file extension for a more accurate mapping.
    """
    # First, try to infer from file extension
    ext_map = {
        ".jsonl": "jsonl",
        ".json": "jsonl",
        ".parquet": "parquet",
        ".npy": "npy",
        ".bin": "bin",
        ".csv": "jsonl",  # CSV can be read line-by-line with adaptation
        ".txt": "jsonl",  # TXT can be read line-by-line
    }
    if file_path:
        for ext, fmt in ext_map.items():
            if file_path.endswith(ext):
                return fmt

    # Fallback: map data_type → training format
    type_map = {
        "text": "jsonl",
        "doc": "jsonl",
        "excel": "jsonl",
        "other": "jsonl",
    }
    return type_map.get(data_type, "jsonl")


def _resolve_dataset_paths(ds) -> list[str]:
    """Return all local data file paths for the dataset, downloading from MinIO if needed.

    **Prefers preprocessed data**: if ``processed/data.jsonl`` exists it is
    returned exclusively.  Otherwise raw data files are returned in sorted order.

    Returns a sorted list of paths, or empty list if nothing found.
    """
    import logging
    logger = logging.getLogger(__name__)
    storage_path = ds.storage_path or ""

    valid_ext = (".jsonl", ".npy", ".bin", ".txt", ".json", ".csv")
    data_files: list[str] = []

    def _find_processed_files(root: str) -> list[str]:
        """Find processed data files under *root*.

        Prefers sharded files (``data_shard_*.jsonl``), falls back to the
        legacy single file (``data.jsonl``). Returns empty list if nothing found.
        """
        processed_dir = os.path.join(root, "processed")
        if not os.path.isdir(processed_dir):
            return []

        shards = sorted(
            os.path.join(processed_dir, fn)
            for fn in os.listdir(processed_dir)
            if fn.startswith("data_shard_") and fn.endswith(".jsonl")
        )
        if shards:
            return shards

        legacy = os.path.join(processed_dir, "data.jsonl")
        if os.path.isfile(legacy):
            return [legacy]

        for dirpath, _, filenames in os.walk(root):
            if "processed" in dirpath.split(os.sep):
                for fn in filenames:
                    if fn.startswith("data_shard_") and fn.endswith(".jsonl"):
                        shards.append(os.path.join(dirpath, fn))
                if shards:
                    return shards
                for fn in filenames:
                    if fn == "data.jsonl":
                        return [os.path.join(dirpath, fn)]
        return []

    def _scan_dir(root: str) -> None:
        """Recursively collect raw data files, skipping processed/."""
        if not os.path.isdir(root):
            return
        for entry in sorted(os.listdir(root)):
            full = os.path.join(root, entry)
            if os.path.isfile(full) and entry.endswith(valid_ext):
                if "/processed/" in full:
                    continue
                data_files.append(full)
            elif os.path.isdir(full) and not entry.startswith(".") and entry != "processed":
                _scan_dir(full)

    # 1. Try local filesystem directly
    if os.path.exists(storage_path):
        if os.path.isfile(storage_path) and storage_path.endswith(valid_ext):
            return [storage_path]
        # Prefer preprocessed data
        processed = _find_processed_files(storage_path)
        if processed:
            return processed
        _scan_dir(storage_path)
        if data_files:
            return data_files

    # 2. Try MinIO download
    local_dir = _download_dataset_from_minio(storage_path)
    if local_dir is not None:
        processed = _find_processed_files(local_dir)
        if processed:
            return processed
        _scan_dir(local_dir)
        if data_files:
            return data_files

    return []


def _resolve_dataset_path(ds) -> str | None:
    """Legacy wrapper returning the first resolved file path."""
    paths = _resolve_dataset_paths(ds)
    return paths[0] if paths else None


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


def _load_pretrained_weights(model, base_model_version_id: int) -> None:
    """Load pretrained model weights from a previous ModelVersion for fine-tuning.

    Downloads checkpoint.pt from MinIO models bucket, then loads the state_dict
    into *model* in-place.  Reports progress to stdout so it appears in task logs.
    """
    import logging
    import tempfile

    _log = logging.getLogger(__name__)

    try:
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.orm import Session as _S
        from app.models.model_version import ModelVersion as _MV
        from app.core.database import get_minio_client

        _engine = _ce(settings.postgres_database_url)
        with _S(_engine) as db:
            mv = db.query(_MV).filter(_MV.id == base_model_version_id).first()
            if mv is None:
                print(
                    f"[TrainingTask] WARNING: base_model_version_id={base_model_version_id} not found, "
                    "training from scratch",
                    flush=True,
                )
                return

            model_code = mv.model_code
            version = mv.version
            storage_path = mv.storage_path  # e.g. "models/my-model/v1.0.0"

        print(
            f"[TrainingTask] Loading pretrained weights from {model_code} {version} "
            f"(storage_path={storage_path})",
            flush=True,
        )

        minio = get_minio_client()
        model_bucket = settings.MINIO_BUCKET_MODELS

        # Check if checkpoint exists in MinIO
        ckpt_object = f"{storage_path}/checkpoint.pt"
        local_dir = tempfile.mkdtemp(prefix="finetune_ckpt_")
        local_path = os.path.join(local_dir, "checkpoint.pt")

        minio.fget_object(model_bucket, ckpt_object, local_path)
        print(f"[TrainingTask] Downloaded checkpoint from MinIO: {ckpt_object}", flush=True)

        checkpoint = torch.load(local_path, map_location="cpu")
        # The checkpoint may wrap state_dict under a "model" key (PyTorchTrainer
        # convention) or be a raw state_dict.
        if "model" in checkpoint:
            state_dict = checkpoint["model"]
        elif "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint

        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        if missing:
            print(f"[TrainingTask] Missing keys (will use random init): {missing}", flush=True)
        if unexpected:
            print(f"[TrainingTask] Unexpected keys (ignored): {unexpected}", flush=True)
        print(
            f"[TrainingTask] Successfully loaded pretrained weights from {model_code} {version}",
            flush=True,
        )

        import shutil
        shutil.rmtree(local_dir, ignore_errors=True)
    except Exception as exc:
        print(
            f"[TrainingTask] WARNING: Failed to load pretrained weights: {exc}. "
            "Training from scratch.",
            flush=True,
        )
        _log.exception("_load_pretrained_weights failed")


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
            "influxdb_timeout_ms": settings.INFLUXDB_TIMEOUT_MS,
            # Ensure training subprocesses/threads can update Postgres progress
            "postgres_db_url": settings.postgres_database_url,
        },
    }

    # Map flat keys to nested structure
    model_keys = {
        "vocab_size", "hidden_size", "num_layers",
        "num_attention_heads", "intermediate_size", "seq_length",
        "max_position_embeddings", "dropout", "layer_norm_eps", "activation",
    }
    data_keys = {
        "dataset_path", "dataset_paths", "dataset_format", "train_split", "seed", "num_workers", "pin_memory",
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
        "checkpoint_dir",
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
        elif key == "base_model_version_id":
            config["base_model_version_id"] = value

    config["model"]["model_type"] = "gpt2"
    return config


def _store_total_steps(task_code: str, total_steps: int, steps_per_epoch: int) -> None:
    """Store total_steps and steps_per_epoch in the task's config_json for progress bar."""
    import json as _json
    try:
        from sqlalchemy import create_engine as _ce, text as _txt
        from sqlalchemy.orm import Session as _S
        _engine = _ce(settings.postgres_database_url)
        with _S(_engine) as db:
            row = db.execute(
                _txt("SELECT config_json FROM training_tasks WHERE task_code = :tc"),
                {"tc": task_code},
            ).fetchone()
            if row is None:
                return
            raw = row[0]
            if isinstance(raw, str):
                cfg = _json.loads(raw) if raw else {}
            elif isinstance(raw, dict):
                cfg = dict(raw)
            else:
                cfg = {}
            cfg["_total_steps"] = total_steps
            cfg["_steps_per_epoch"] = steps_per_epoch
            db.execute(
                _txt("UPDATE training_tasks SET config_json = :cfg WHERE task_code = :tc"),
                {"cfg": _json.dumps(cfg, ensure_ascii=False), "tc": task_code},
            )
            db.commit()
    except Exception:
        pass


def _update_task_status(
    task_code: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update TrainingTask status in PostgreSQL directly via SQLAlchemy."""
    try:
        from datetime import datetime as _dt, timezone as _tz
        from sqlalchemy import create_engine as _ce, update as _upd
        from sqlalchemy.orm import Session as _S
        from app.models.training_task import TrainingTask as _TT
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


def _promote_to_model(task_code: str) -> dict | None:
    """Promote training checkpoints to a ModelVersion after successful training.

    Copies checkpoint files from the checkpoints bucket to the models bucket
    in MinIO, then creates a ModelVersion record linked to the training task.
    """
    import logging
    import re

    logger = logging.getLogger(__name__)

    try:
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.orm import Session as _S
        from app.models.training_task import TrainingTask as _TT
        from app.repositories import model_repository

        _engine = _ce(settings.postgres_database_url)
        with _S(_engine) as db:
            task = db.query(_TT).filter(_TT.task_code == task_code).first()
            if task is None:
                return None

            # Check if already promoted
            existing = (
                db.query(model_repository.ModelVersion)
                .filter(model_repository.ModelVersion.task_id == task.id)
                .first()
            )
            if existing:
                logger.info("Task %s already promoted to model %s v%s", task_code, existing.model_code, existing.version)
                return {"model_code": existing.model_code, "version": existing.version, "id": existing.id}

            config = task.config_json or {}
            model_type = "gpt2"
            framework = task.framework or "pytorch"

            # If this was a fine-tune task, reuse the base model's model_code
            # so the new version goes into the same model's version history.
            base_model_version_id = config.get("base_model_version_id")
            if base_model_version_id is not None:
                base_mv = (
                    db.query(model_repository.ModelVersion)
                    .filter(model_repository.ModelVersion.id == base_model_version_id)
                    .first()
                )
                if base_mv is not None:
                    model_code = base_mv.model_code
                    model_name = base_mv.model_name
                else:
                    model_code = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "-", task.task_name.lower())
                    model_code = re.sub(r"-+", "-", model_code).strip("-")
                    if not model_code:
                        model_code = f"model-{task_code.lower()}"
                    model_name = task.task_name
            else:
                # Generate model_code from task_name (sanitize for use as model code)
                model_code = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "-", task.task_name.lower())
                model_code = re.sub(r"-+", "-", model_code).strip("-")
                if not model_code:
                    model_code = f"model-{task_code.lower()}"
                model_name = task.task_name

            # Build structured hyperparams from training config
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

            # Copy checkpoints from checkpoints bucket → models bucket
            version_str = model_repository.auto_version(db, model_code)
            storage_path = f"models/{model_code}/{version_str}"

            ckpt_uploaded = False

            def _upload_local_tokenizer_vocab(minio, model_bucket: str) -> None:
                candidates = [
                    "/tmp/llmt_checkpoints/ckpt/tokenizer_vocab.json",
                    "/tmp/llmt_checkpoints/tokenizer_vocab.json",
                    "./checkpoints/ckpt/tokenizer_vocab.json",
                    "./checkpoints/tokenizer_vocab.json",
                ]
                # DeepSpeed convention: latest file points to step-N directory
                for base in ("/tmp/llmt_checkpoints", "./checkpoints"):
                    latest_file = os.path.join(base, "latest")
                    if os.path.isfile(latest_file):
                        with open(latest_file, "r") as f:
                            latest_dir = f.read().strip()
                        candidates.append(
                            os.path.join(base, latest_dir, "tokenizer_vocab.json"),
                        )
                # Also scan checkpoints/ for any step subdirectory
                for ckpt_root in ("./checkpoints", "/tmp/llmt_checkpoints"):
                    if os.path.isdir(ckpt_root):
                        for entry in sorted(os.listdir(ckpt_root), reverse=True):
                            entry_path = os.path.join(ckpt_root, entry)
                            if os.path.isdir(entry_path) and entry.startswith("step-"):
                                candidates.append(
                                    os.path.join(entry_path, "tokenizer_vocab.json"),
                                )
                for vocab_path in candidates:
                    if os.path.isfile(vocab_path):
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
                    if not os.path.isdir(tokenizer_dir):
                        continue
                    for root, _dirs, files in os.walk(tokenizer_dir):
                        for fn in files:
                            local_path = os.path.join(root, fn)
                            rel = os.path.relpath(local_path, tokenizer_dir)
                            object_name = f"{storage_path}/tokenizer/{rel}".replace("\\", "/")
                            minio.fput_object(model_bucket, object_name, local_path)
                    logger.info("Uploaded tokenizer directory %s -> %s/%s/tokenizer", tokenizer_dir, model_bucket, storage_path)
                    break

            try:
                from app.core.database import get_minio_client
                from minio.commonconfig import CopySource

                minio = get_minio_client()
                ckpt_bucket = settings.MINIO_BUCKET_CHECKPOINTS
                model_bucket = settings.MINIO_BUCKET_MODELS
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
                        logger.info("Copied latest checkpoint (%d files): %s -> %s", len(selected_files), f"{ckpt_bucket}/{prefix}{latest_group}", f"{model_bucket}/{storage_path}")
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

            # Fallback: upload from local checkpoint directories if MinIO copy failed
            local_ckpt_dirs = [
                "/tmp/llmt_checkpoints/ckpt",
                "/tmp/llmt_checkpoints/latest",
                "/tmp/llmt_checkpoints",
                "./checkpoints",
                "./checkpoints/step-500",
            ]
            # Also include any DeepSpeed step subdirectories under ./checkpoints/
            if os.path.isdir("./checkpoints"):
                latest_file = os.path.join("./checkpoints", "latest")
                if os.path.isfile(latest_file):
                    with open(latest_file, "r") as f:
                        latest_dir = f.read().strip()
                    local_ckpt_dirs.append(os.path.join("./checkpoints", latest_dir))
            if not ckpt_uploaded:
                try:
                    minio = get_minio_client()
                    model_bucket = settings.MINIO_BUCKET_MODELS
                    for local_dir in local_ckpt_dirs:
                        if not os.path.isdir(local_dir):
                            continue
                        for root, _dirs, files in os.walk(local_dir):
                            for fn in files:
                                local_path = os.path.join(root, fn)
                                rel = os.path.relpath(local_path, local_dir)
                                object_name = f"{storage_path}/{rel}".replace("\\", "/")
                                minio.fput_object(model_bucket, object_name, local_path)
                        _upload_local_tokenizer_vocab(minio, model_bucket)
                        ckpt_uploaded = True
                        logger.info("Uploaded local checkpoint %s -> %s/%s", local_dir, model_bucket, storage_path)
                        break
                except Exception as exc:
                    logger.warning("Local checkpoint upload failed: %s", exc)

            if not ckpt_uploaded:
                logger.info("No checkpoint files found, model version created without weights")

            # Build metrics placeholder (will be populated from actual training metrics)
            metrics: dict[str, Any] = {}

            model = model_repository.create_model(
                db,
                model_name=model_name,
                model_code=model_code,
                tag=f"auto-{task_code}",
                description=f"自动从训练任务 {task_code} 创建",
                framework=framework,
                metrics=metrics,
                training_metadata=hyperparams,
                task_id=task.id,
                creator_id=task.creator_id,
            )

            logger.info("Promoted training task %s to model %s v%s (id=%d)", task_code, model_code, model.version, model.id)
            return {"model_code": model_code, "version": model.version, "id": model.id}

    except Exception as exc:
        logger.warning("Failed to promote task %s to model: %s", task_code, exc)
        return None


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

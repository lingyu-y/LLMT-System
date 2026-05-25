"""DeepSpeed Trainer – ZeRO 1/2/3 + CPU offload support."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import torch
import torch.nn as nn
import torch.distributed as dist
from torch.utils.data import DataLoader, DistributedSampler

from llmt_training.core.base_trainer import BaseTrainer
from llmt_training.core.callbacks import CallbackList
from llmt_training.core.state import TrainingState
from llmt_training.config.schema import TrainingConfig
from llmt_training.config.merger import ConfigMerger


class DeepSpeedTrainer(BaseTrainer):
    """DeepSpeed trainer supporting ZeRO stages 1/2/3 and CPU offloading.

    Uses deepspeed.initialize() to wrap model, optimizer, dataloader, and scheduler.
    """

    def __init__(
        self,
        config: dict[str, Any],
        model: nn.Module | None = None,
        train_dataloader: DataLoader | None = None,
        eval_dataloader: DataLoader | None = None,
        callbacks: CallbackList | None = None,
        state: TrainingState | None = None,
        loss_fn: nn.Module | None = None,
        ds_config: dict[str, Any] | None = None,
    ):
        super().__init__(config, model, train_dataloader, eval_dataloader, callbacks, state)
        self.loss_fn = loss_fn or nn.CrossEntropyLoss()
        self._ds_config = ds_config  # Pre-built DeepSpeed config, or None (will generate)
        self._ds_engine = None

    def _get_or_build_ds_config(self) -> dict[str, Any]:
        """Return the DeepSpeed config dict, generating one if not provided."""
        if self._ds_config is not None:
            return self._ds_config

        # Build from TrainingConfig
        try:
            tc = TrainingConfig(**self.config)
            return ConfigMerger.to_deepspeed_json(tc)
        except Exception:
            # Fallback: minimal config
            hp = self.config.get("hyperparams", {})
            num_gpus = self.config.get("num_gpus", 1)
            ds_cfg: dict[str, Any] = {
                "train_batch_size": "auto",
                "train_micro_batch_size_per_gpu": "auto",
                "gradient_accumulation_steps": "auto",
                "gradient_clipping": hp.get("max_grad_norm", 1.0),
                "fp16": {"enabled": hp.get("precision") == "fp16"},
                "bf16": {"enabled": hp.get("precision") == "bf16"},
                "optimizer": {
                    "type": "AdamW",
                    "params": {
                        "lr": hp.get("learning_rate", 2e-5),
                        "betas": [hp.get("beta1", 0.9), hp.get("beta2", 0.999)],
                        "eps": hp.get("adam_epsilon", 1e-8),
                        "weight_decay": hp.get("weight_decay", 0.01),
                        "torch_adam": True,
                    },
                },
            }
            # For single-GPU, skip ZeRO to avoid dist.new_group([0]) failures
            # that occur in some PyTorch + DeepSpeed combinations.
            if num_gpus > 1:
                ds_cfg["zero_optimization"] = {"stage": 2}
            return ds_cfg

    @staticmethod
    def _estimate_total_steps(
        hp: dict[str, Any],
        train_dataloader: DataLoader | None,
    ) -> int:
        """Resolve the exact training step budget used by both loop and scheduler."""
        max_steps = hp.get("max_steps")
        if max_steps:
            return int(max_steps)

        max_epochs = int(hp.get("max_epochs", 10))
        if train_dataloader is not None:
            try:
                return max(1, max_epochs * len(train_dataloader))
            except TypeError:
                pass
        return max(1, max_epochs * 1000)

    @staticmethod
    def _sync_scheduler_steps(
        ds_config: dict[str, Any],
        hp: dict[str, Any],
        total_steps: int,
    ) -> None:
        """Make DeepSpeed scheduler use the same step budget as the trainer loop."""
        scheduler = ds_config.get("scheduler")
        if not isinstance(scheduler, dict):
            return

        params = scheduler.setdefault("params", {})
        warmup_steps = min(int(hp.get("warmup_steps", 1000)), total_steps)
        learning_rate = float(hp.get("learning_rate", 2e-5))
        params["warmup_num_steps"] = warmup_steps
        params["total_num_steps"] = total_steps
        params["warmup_max_lr"] = learning_rate
        params["warmup_min_lr"] = learning_rate / max(warmup_steps, 1)

    def train(self) -> TrainingState:
        """Run the DeepSpeed training loop."""
        import deepspeed

        self.state.status = "running"
        self.callbacks.on_train_begin(self.state)

        ds_config = self._get_or_build_ds_config()
        hp = self.config.get("hyperparams", {})
        max_epochs = int(hp.get("max_epochs", 10))
        total_steps = self._estimate_total_steps(hp, self.train_dataloader)
        self._sync_scheduler_steps(ds_config, hp, total_steps)
        scheduler_params = ds_config.get("scheduler", {}).get("params", {})
        print(
            "[DeepSpeedTrainer] scheduler ready: "
            f"total_steps={scheduler_params.get('total_num_steps', total_steps)} "
            f"warmup_steps={scheduler_params.get('warmup_num_steps')}",
            flush=True,
        )

        # Write ds_config to temp file (required by deepspeed.initialize in some cases)
        ds_config_path = os.path.join(
            self.config.get("checkpoint", {}).get("checkpoint_dir", "/tmp/llmt_checkpoints"),
            "ds_config.json",
        )
        os.makedirs(os.path.dirname(ds_config_path), exist_ok=True)
        with open(ds_config_path, "w") as f:
            json.dump(ds_config, f, indent=2)

        # Determine local rank
        local_rank = int(os.environ.get("LOCAL_RANK", 0))

        # Check CUDA availability (including driver compatibility)
        use_cuda = False
        if torch.cuda.is_available():
            try:
                # Try a small CUDA operation to verify driver compatibility
                _test = torch.zeros(1, device="cuda")
                del _test
                use_cuda = True
            except (RuntimeError, torch.cuda.CudaError) as e:
                import logging
                logging.getLogger(__name__).warning(
                    "CUDA runtime available but driver incompatible (%s). Falling back to CPU.", e,
                )
                use_cuda = False

        device = torch.device(f"cuda:{local_rank}" if use_cuda else "cpu")
        if use_cuda:
            torch.cuda.set_device(local_rank)

        # If running on CPU, adjust DeepSpeed config to avoid CUDA-only features
        if not use_cuda:
            ds_config["fp16"] = {"enabled": False}
            ds_config["bf16"] = {"enabled": False}

        # Move model to correct device before init
        self.model = self.model.to(device)
        print(f"[DeepSpeedTrainer] initializing DeepSpeed on device={device}", flush=True)

        # Ensure distributed init environment variables are set (required by DeepSpeed)
        os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
        os.environ.setdefault("MASTER_PORT", "29500")
        os.environ.setdefault("LOCAL_RANK", str(local_rank))
        os.environ.setdefault("RANK", "0")
        os.environ.setdefault("WORLD_SIZE", "1")

        # Save original sampler before training starts.
        _train_sampler = getattr(self.train_dataloader, "sampler", None) if self.train_dataloader is not None else None

        # Initialize torch.distributed before DeepSpeed to avoid MPI detection
        if not torch.distributed.is_initialized():
            backend = "nccl" if use_cuda else "gloo"
            torch.distributed.init_process_group(
                backend=backend,
                rank=0,
                world_size=1,
            )

        model_engine, optimizer, train_dataloader, scheduler = deepspeed.initialize(
            model=self.model,
            model_parameters=[p for p in self.model.parameters() if p.requires_grad],
            config=ds_config,
        )
        print("[DeepSpeedTrainer] DeepSpeed initialized, entering training loop", flush=True)
        self._ds_engine = model_engine
        self.train_dataloader = train_dataloader or self.train_dataloader

        start_time = time.time()

        try:
            for epoch in range(self.state.epoch, max_epochs):
                self.state.epoch = epoch
                self.callbacks.on_epoch_begin(self.state)

                if isinstance(_train_sampler, DistributedSampler):
                    _train_sampler.set_epoch(epoch)

                for step, batch in enumerate(self.train_dataloader):
                    if self.state.global_step == 0 and step == 0:
                        print("[DeepSpeedTrainer] first batch received", flush=True)
                    if self._should_stop():
                        break
                    if total_steps and self.state.global_step >= total_steps:
                        break

                    # Move batch to device
                    batch = {k: v.to(model_engine.device) if isinstance(v, torch.Tensor) else v
                             for k, v in batch.items()}
                    if "input_ids" in batch and isinstance(batch["input_ids"], torch.Tensor):
                        batch["input_ids"] = batch["input_ids"].long()
                    if "attention_mask" in batch and isinstance(batch["attention_mask"], torch.Tensor):
                        batch["attention_mask"] = batch["attention_mask"].long()
                    if "labels" in batch and isinstance(batch["labels"], torch.Tensor):
                        batch["labels"] = batch["labels"].long()

                    # Forward
                    outputs = model_engine(**{k: v for k, v in batch.items()
                                              if k in ("input_ids", "attention_mask")})

                    loss = self.loss_fn(
                        outputs.logits.view(-1, outputs.logits.size(-1)),
                        batch["labels"].view(-1),
                    )
                    # Backward + step via DeepSpeed engine
                    model_engine.backward(loss)
                    model_engine.step()

                    # Update state
                    self.state.global_step += 1
                    self.state.loss = loss.item()
                    self.state.learning_rate = optimizer.param_groups[0]["lr"]
                    self.state.elapsed_seconds = time.time() - start_time

                    log_interval = max(1, int(hp.get("log_interval", 10)))
                    if self.state.global_step == 1 or self.state.global_step % log_interval == 0:
                        print(
                            "[DeepSpeedTrainer] "
                            f"step={self.state.global_step}/{total_steps} "
                            f"epoch={epoch} loss={self.state.loss:.4f} "
                            f"lr={self.state.learning_rate:.3e} "
                            f"elapsed={self.state.elapsed_seconds:.1f}s",
                            flush=True,
                        )

                    self.callbacks.on_step_end(
                        self.state,
                        loss=self.state.loss,
                        lr=self.state.learning_rate,
                    )

                    # Checkpoint
                    ckpt_cfg = self.config.get("checkpoint", {})
                    save_interval = ckpt_cfg.get("save_interval", 500)
                    if self.state.global_step % save_interval == 0:
                        ckpt_dir = ckpt_cfg.get("checkpoint_dir", "/tmp/llmt_checkpoints")
                        self.save_checkpoint(ckpt_dir)

                self.callbacks.on_epoch_end(self.state)

                if self._should_stop():
                    break
                if total_steps and self.state.global_step >= total_steps:
                    break

            if self.state.status not in ("cancelled", "failed", "paused"):
                self.state.status = "completed"
                if self.state.global_step > 0:
                    ckpt_dir = self.config.get("checkpoint", {}).get(
                        "checkpoint_dir", "/tmp/llmt_checkpoints",
                    )
                    self.save_checkpoint(ckpt_dir)

        except Exception as e:
            self.state.status = "failed"
            self.state.error_message = str(e)
            self.callbacks.on_error(self.state, error=e)

        self.callbacks.on_train_end(self.state)
        # Free GPU memory so subsequent runs or resume don't OOM
        self._cleanup_gpu()
        return self.state

    def _cleanup_gpu(self):
        """Release GPU memory held by the DeepSpeed engine and model."""
        if self._ds_engine is not None:
            try:
                self._ds_engine.empty_partition_cache()
            except Exception:
                pass
            self._ds_engine = None
        self.model = None
        self.train_dataloader = None
        self.eval_dataloader = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            # Release the CUDA memory pool to give memory back to the OS
            try:
                torch.cuda.reset_peak_memory_stats()
                if hasattr(torch.cuda, 'memory') and hasattr(torch.cuda.memory, 'caching_allocator_delete'):
                    pass  # API not stable, worst case nothing happens
            except Exception:
                pass

    def evaluate(self) -> dict[str, float]:
        """Run evaluation with DeepSpeed engine."""
        if self.eval_dataloader is None or self._ds_engine is None:
            return {}

        self._ds_engine.eval()
        total_loss = 0.0
        total_steps = 0

        with torch.no_grad():
            for batch in self.eval_dataloader:
                batch = {k: v.to(self._ds_engine.device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                outputs = self._ds_engine(**{k: v for k, v in batch.items()
                                             if k in ("input_ids", "attention_mask")})
                loss = self.loss_fn(
                    outputs.logits.view(-1, outputs.logits.size(-1)),
                    batch["labels"].view(-1),
                )
                total_loss += loss.item()
                total_steps += 1

        self._ds_engine.train()
        return {"eval_loss": total_loss / max(total_steps, 1)}

    def save_checkpoint(self, path: str) -> str:
        """Save DeepSpeed checkpoint — overwrites previous one."""
        if self._ds_engine is None:
            return ""
        os.makedirs(path, exist_ok=True)
        tag = "ckpt"
        ckpt_path = os.path.join(path, tag)
        if os.path.exists(ckpt_path):
            import shutil
            if os.path.isdir(ckpt_path):
                shutil.rmtree(ckpt_path)
            else:
                os.remove(ckpt_path)
        self._ds_engine.save_checkpoint(path, tag=tag)
        self.callbacks.on_checkpoint(self.state, checkpoint_path=ckpt_path)
        return ckpt_path

    def load_checkpoint(self, path: str) -> None:
        """Load DeepSpeed checkpoint."""
        if self._ds_engine is None:
            return
        self._ds_engine.load_checkpoint(path)

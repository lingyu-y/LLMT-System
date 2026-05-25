"""PyTorch DDP Trainer – single-GPU or standard distributed data parallel."""

from __future__ import annotations

import os
import time
from typing import Any

import torch
import torch.nn as nn
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler

from llmt_training.core.base_trainer import BaseTrainer
from llmt_training.core.callbacks import CallbackList
from llmt_training.core.state import TrainingState


class PyTorchTrainer(BaseTrainer):
    """Standard PyTorch DDP trainer for single-GPU or multi-GPU data parallel training."""

    def __init__(
        self,
        config: dict[str, Any],
        model: nn.Module | None = None,
        train_dataloader: DataLoader | None = None,
        eval_dataloader: DataLoader | None = None,
        callbacks: CallbackList | None = None,
        state: TrainingState | None = None,
        loss_fn: nn.Module | None = None,
    ):
        super().__init__(config, model, train_dataloader, eval_dataloader, callbacks, state)
        self.loss_fn = loss_fn or nn.CrossEntropyLoss()
        self.device = self._get_device()
        self._is_distributed = dist.is_initialized()
        self._optimizer: torch.optim.Optimizer | None = None
        self._scheduler: torch.optim.lr_scheduler.LRScheduler | None = None
        self._scaler: torch.cuda.amp.GradScaler | None = None

    @staticmethod
    def _get_device() -> torch.device:
        if torch.cuda.is_available():
            local_rank = int(os.environ.get("LOCAL_RANK", 0))
            return torch.device(f"cuda:{local_rank}")
        return torch.device("cpu")

    def _setup_model(self) -> nn.Module:
        """Move model to device and wrap with DDP if distributed."""
        model = self.model.to(self.device)
        if self._is_distributed:
            model = DDP(
                model,
                device_ids=[self.device] if self.device.type == "cuda" else None,
                output_device=self.device if self.device.type == "cuda" else None,
            )
        return model

    def _build_optimizer(self, model: nn.Module) -> torch.optim.Optimizer:
        """Build optimizer from config."""
        hp = self.config.get("hyperparams", {})
        opt_name = hp.get("optimizer", "adamw")
        lr = hp.get("learning_rate", 2e-5)
        wd = hp.get("weight_decay", 0.01)

        # Separate decay and no-decay parameters
        decay_params = []
        no_decay_params = []
        for name, param in model.named_parameters():
            if not param.requires_grad:
                continue
            if "bias" in name or "LayerNorm" in name or "layer_norm" in name:
                no_decay_params.append(param)
            else:
                decay_params.append(param)

        param_groups = [
            {"params": decay_params, "weight_decay": wd},
            {"params": no_decay_params, "weight_decay": 0.0},
        ]

        if opt_name == "adamw":
            return torch.optim.AdamW(
                param_groups, lr=lr,
                betas=(hp.get("beta1", 0.9), hp.get("beta2", 0.999)),
                eps=hp.get("adam_epsilon", 1e-8),
            )
        elif opt_name == "adam":
            return torch.optim.Adam(param_groups, lr=lr)
        elif opt_name == "sgd":
            return torch.optim.SGD(param_groups, lr=lr)
        else:
            return torch.optim.AdamW(param_groups, lr=lr)

    def _build_scheduler(
        self, optimizer: torch.optim.Optimizer, total_steps: int,
    ) -> torch.optim.lr_scheduler.LambdaLR | None:
        """Build LR scheduler from config."""
        hp = self.config.get("hyperparams", {})
        scheduler_type = hp.get("scheduler", "linear_warmup_decay")
        warmup_steps = hp.get("warmup_steps", 1000)
        min_lr_ratio = hp.get("min_lr", 0.0) / max(hp.get("learning_rate", 2e-5), 1e-10)
        warmup_steps = min(warmup_steps, max(total_steps, 1))

        def _linear_warmup_decay(step: int) -> float:
            if step < warmup_steps:
                return (step + 1) / max(warmup_steps, 1)
            progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
            return max(min_lr_ratio, 1.0 - progress)

        def _cosine(step: int) -> float:
            if step < warmup_steps:
                return (step + 1) / max(warmup_steps, 1)
            progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
            return max(min_lr_ratio, 0.5 * (1.0 + __import__("math").cos(__import__("math").pi * progress)))

        def _constant_warmup(step: int) -> float:
            if step < warmup_steps:
                return (step + 1) / max(warmup_steps, 1)
            return 1.0

        fn_map = {
            "linear_warmup_decay": _linear_warmup_decay,
            "cosine": _cosine,
            "constant_warmup": _constant_warmup,
            "polynomial": _linear_warmup_decay,  # simplified
        }
        fn = fn_map.get(scheduler_type, _linear_warmup_decay)
        return torch.optim.lr_scheduler.LambdaLR(optimizer, fn)

    def train(self) -> TrainingState:
        """Run the training loop."""
        self.state.status = "running"
        self.callbacks.on_train_begin(self.state)

        model = self._setup_model()
        optimizer = self._build_optimizer(model)
        self._optimizer = optimizer

        hp = self.config.get("hyperparams", {})
        max_epochs = hp.get("max_epochs", 10)
        max_steps = hp.get("max_steps")
        grad_accum = hp.get("gradient_accumulation_steps", 1)
        max_grad_norm = hp.get("max_grad_norm", 1.0)
        precision = hp.get("precision", "fp16")

        total_steps_estimate = max_steps or (max_epochs * len(self.train_dataloader))
        scheduler = self._build_scheduler(optimizer, total_steps_estimate)
        self._scheduler = scheduler

        scaler = None
        if precision == "fp16" and self.device.type == "cuda":
            try:
                from torch.cuda.amp import GradScaler as _GradScaler
                scaler = _GradScaler()
            except Exception:
                try:
                    scaler = torch.amp.GradScaler()
                except Exception:
                    scaler = None
        self._scaler = scaler

        start_time = time.time()

        try:
            for epoch in range(self.state.epoch, max_epochs):
                self.state.epoch = epoch
                self.callbacks.on_epoch_begin(self.state)

                if isinstance(self.train_dataloader.sampler, DistributedSampler):
                    self.train_dataloader.sampler.set_epoch(epoch)

                optimizer.zero_grad()
                for step, batch in enumerate(self.train_dataloader):
                    if self._should_stop():
                        break
                    if total_steps_estimate and self.state.global_step >= total_steps_estimate:
                        break

                    # Move batch to device
                    batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                             for k, v in batch.items()}

                    # Ensure model input ids are integer tensors for embedding lookup
                    if "input_ids" in batch and isinstance(batch["input_ids"], torch.Tensor):
                        batch["input_ids"] = batch["input_ids"].long()
                    if "attention_mask" in batch and isinstance(batch["attention_mask"], torch.Tensor):
                        batch["attention_mask"] = batch["attention_mask"].long()
                    if "labels" in batch and isinstance(batch["labels"], torch.Tensor):
                        batch["labels"] = batch["labels"].long()

                    # Forward
                    if scaler is not None:
                        with torch.amp.autocast("cuda"):
                            outputs = model(**{k: v for k, v in batch.items()
                                              if k in ("input_ids", "attention_mask")})
                            loss = self.loss_fn(
                                outputs.logits.view(-1, outputs.logits.size(-1)),
                                batch["labels"].view(-1),
                            ) / grad_accum
                        scaler.scale(loss).backward()
                    else:
                        outputs = model(**{k: v for k, v in batch.items()
                                          if k in ("input_ids", "attention_mask")})
                        loss = self.loss_fn(
                            outputs.logits.view(-1, outputs.logits.size(-1)),
                            batch["labels"].view(-1),
                        ) / grad_accum
                        loss.backward()

                    # Gradient accumulation
                    if (step + 1) % grad_accum == 0:
                        if scaler is not None:
                            scaler.unscale_(optimizer)
                            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
                            scaler.step(optimizer)
                            scaler.update()
                        else:
                            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
                            optimizer.step()
                        if scheduler is not None:
                            scheduler.step()
                        optimizer.zero_grad()

                    # Update state
                    self.state.global_step += 1
                    self.state.loss = loss.item() * grad_accum
                    self.state.learning_rate = optimizer.param_groups[0]["lr"]
                    self.state.elapsed_seconds = time.time() - start_time

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
                        ckpt_path = self.save_checkpoint(ckpt_dir)

                self.callbacks.on_epoch_end(self.state)

                if self._should_stop():
                    break
                if total_steps_estimate and self.state.global_step >= total_steps_estimate:
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
        self._cleanup_gpu()
        return self.state

    def _cleanup_gpu(self):
        """Release GPU memory held by model, optimizer, and scaler."""
        self.model = None
        self.train_dataloader = None
        self.eval_dataloader = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            try:
                torch.cuda.reset_peak_memory_stats()
            except Exception:
                pass

    def evaluate(self) -> dict[str, float]:
        """Run evaluation loop."""
        if self.eval_dataloader is None:
            return {}

        model = self.model if not isinstance(self.model, DDP) else self.model.module
        model.eval()
        total_loss = 0.0
        total_steps = 0

        with torch.no_grad():
            for batch in self.eval_dataloader:
                batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                         for k, v in batch.items()}
                if "input_ids" in batch and isinstance(batch["input_ids"], torch.Tensor):
                    batch["input_ids"] = batch["input_ids"].long()
                if "attention_mask" in batch and isinstance(batch["attention_mask"], torch.Tensor):
                    batch["attention_mask"] = batch["attention_mask"].long()
                if "labels" in batch and isinstance(batch["labels"], torch.Tensor):
                    batch["labels"] = batch["labels"].long()
                outputs = model(**{k: v for k, v in batch.items()
                                  if k in ("input_ids", "attention_mask")})
                loss = self.loss_fn(
                    outputs.logits.view(-1, outputs.logits.size(-1)),
                    batch["labels"].view(-1),
                )
                total_loss += loss.item()
                total_steps += 1

        model.train()
        return {"eval_loss": total_loss / max(total_steps, 1)}

    def save_checkpoint(self, path: str) -> str:
        """Save checkpoint to a directory (matching DeepSpeed's structure).

        Saves to ``path/ckpt/`` so that the MinIO upload callback can walk
        the directory and upload all files inside.
        """
        os.makedirs(path, exist_ok=True)
        model = self.model if not isinstance(self.model, DDP) else self.model.module
        tag = "ckpt"
        ckpt_path = os.path.join(path, tag)
        if os.path.exists(ckpt_path):
            import shutil
            if os.path.isdir(ckpt_path):
                shutil.rmtree(ckpt_path)
            else:
                os.remove(ckpt_path)
        os.makedirs(ckpt_path, exist_ok=True)

        checkpoint_data: dict[str, Any] = {
            "model_state_dict": model.state_dict(),
            "epoch": self.state.epoch,
            "global_step": self.state.global_step,
            "loss": self.state.loss,
        }
        if self._optimizer is not None:
            checkpoint_data["optimizer_state_dict"] = self._optimizer.state_dict()
        if self._scheduler is not None:
            checkpoint_data["scheduler_state_dict"] = self._scheduler.state_dict()
        if self._scaler is not None:
            checkpoint_data["scaler_state_dict"] = self._scaler.state_dict()

        torch.save(checkpoint_data, os.path.join(ckpt_path, "checkpoint.pt"))
        self.callbacks.on_checkpoint(self.state, checkpoint_path=ckpt_path)
        return ckpt_path

    def load_checkpoint(self, path: str) -> None:
        """Load checkpoint from a file or directory.

        Supports both the old single-file format (``path/checkpoint.pt``) and
        the new directory format (``path/ckpt/checkpoint.pt``).
        """
        model = self.model if not isinstance(self.model, DDP) else self.model.module

        # Resolve the actual .pt file
        if os.path.isdir(path):
            ckpt_file = os.path.join(path, "checkpoint.pt")
        elif path.endswith(".pt"):
            ckpt_file = path
        else:
            ckpt_file = os.path.join(path, "checkpoint.pt")

        if not os.path.isfile(ckpt_file):
            raise FileNotFoundError(f"Checkpoint file not found: {ckpt_file}")

        checkpoint = torch.load(ckpt_file, map_location=self.device, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        self.state.epoch = checkpoint.get("epoch", 0)
        self.state.global_step = checkpoint.get("global_step", 0)
        self.state.loss = checkpoint.get("loss", 0.0)

        if self._optimizer is not None and "optimizer_state_dict" in checkpoint:
            self._optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        if self._scheduler is not None and "scheduler_state_dict" in checkpoint:
            self._scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        if self._scaler is not None and "scaler_state_dict" in checkpoint:
            self._scaler.load_state_dict(checkpoint["scaler_state_dict"])

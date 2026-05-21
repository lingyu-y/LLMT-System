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
            return {
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
                    },
                },
                "zero_optimization": {"stage": 2},
            }

    def train(self) -> TrainingState:
        """Run the DeepSpeed training loop."""
        import deepspeed

        self.state.status = "running"
        self.callbacks.on_train_begin(self.state)

        ds_config = self._get_or_build_ds_config()

        # Write ds_config to temp file (required by deepspeed.initialize in some cases)
        ds_config_path = os.path.join(
            self.config.get("checkpoint", {}).get("checkpoint_dir", "./checkpoints"),
            "ds_config.json",
        )
        os.makedirs(os.path.dirname(ds_config_path), exist_ok=True)
        with open(ds_config_path, "w") as f:
            json.dump(ds_config, f, indent=2)

        # Determine local rank
        local_rank = int(os.environ.get("LOCAL_RANK", 0))
        device = torch.device(f"cuda:{local_rank}" if torch.cuda.is_available() else "cpu")

        # Move model to correct device before init
        self.model = self.model.to(device)

        # DeepSpeed initialize
        model_engine, optimizer, train_dataloader, scheduler = deepspeed.initialize(
            model=self.model,
            model_parameters=[p for p in self.model.parameters() if p.requires_grad],
            training_data=self.train_dataloader,
            config=ds_config,
            dist_init_address=os.environ.get("MASTER_ADDR", "127.0.0.1"),
            dist_init_port=os.environ.get("MASTER_PORT", "29500"),
        )
        self._ds_engine = model_engine
        self.train_dataloader = train_dataloader or self.train_dataloader

        hp = self.config.get("hyperparams", {})
        max_epochs = hp.get("max_epochs", 10)
        max_steps = hp.get("max_steps")
        grad_accum = hp.get("gradient_accumulation_steps", 1)
        max_grad_norm = hp.get("max_grad_norm", 1.0)

        start_time = time.time()

        try:
            for epoch in range(self.state.epoch, max_epochs):
                self.state.epoch = epoch
                self.callbacks.on_epoch_begin(self.state)

                if isinstance(self.train_dataloader.sampler, DistributedSampler):
                    self.train_dataloader.sampler.set_epoch(epoch)

                for step, batch in enumerate(self.train_dataloader):
                    if self._should_stop():
                        break

                    # Move batch to device
                    batch = {k: v.to(model_engine.device) if isinstance(v, torch.Tensor) else v
                             for k, v in batch.items()}

                    # Forward
                    outputs = model_engine(**{k: v for k, v in batch.items()
                                              if k in ("input_ids", "attention_mask")})
                    loss = self.loss_fn(
                        outputs.logits.view(-1, outputs.logits.size(-1)),
                        batch["labels"].view(-1),
                    )
                    # Backward (DeepSpeed handles gradient accumulation internally)
                    model_engine.backward(loss)
                    model_engine.step()

                    # Update state
                    self.state.global_step += 1
                    self.state.loss = loss.item()
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
                        ckpt_dir = ckpt_cfg.get("checkpoint_dir", "./checkpoints")
                        self.save_checkpoint(ckpt_dir)

                self.callbacks.on_epoch_end(self.state)

                if max_steps and self.state.global_step >= max_steps:
                    break

            self.state.status = "completed"

        except Exception as e:
            self.state.status = "failed"
            self.state.error_message = str(e)
            self.callbacks.on_error(self.state, error=e)

        self.callbacks.on_train_end(self.state)
        return self.state

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
        """Save DeepSpeed checkpoint."""
        if self._ds_engine is None:
            return ""
        os.makedirs(path, exist_ok=True)
        tag = f"step-{self.state.global_step}"
        self._ds_engine.save_checkpoint(path, tag=tag)
        ckpt_path = os.path.join(path, tag)
        self.callbacks.on_checkpoint(self.state, checkpoint_path=ckpt_path)
        return ckpt_path

    def load_checkpoint(self, path: str) -> None:
        """Load DeepSpeed checkpoint."""
        if self._ds_engine is None:
            return
        self._ds_engine.load_checkpoint(path)

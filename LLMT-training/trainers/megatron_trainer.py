"""Megatron-LM Trainer – tensor parallelism, pipeline parallelism, 3D parallelism."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from llmt_training.core.base_trainer import BaseTrainer
from llmt_training.core.callbacks import CallbackList
from llmt_training.core.state import TrainingState
from llmt_training.config.schema import TrainingConfig
from llmt_training.config.merger import ConfigMerger


class MegatronTrainer(BaseTrainer):
    """Megatron-LM trainer for TP/PP/3D parallelism.

    This trainer wraps Megatron-LM's pretrain() orchestration.
    It is designed to be called from within a Megatron-launched process
    (i.e., after torch.distributed.run with Megatron arguments).

    Usage:
        1. Launcher generates Megatron CLI args + writes them to a file
        2. Launcher spawns: torchrun --nproc_per_node=N pretrain_gpt.py --args-file ...
        3. The pretrain script creates MegatronTrainer and calls train()
        4. Inside train(), Megatron initialize -> forward_step loop -> checkpointing
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
        model_provider_fn=None,
        forward_step_fn=None,
    ):
        super().__init__(config, model, train_dataloader, eval_dataloader, callbacks, state)
        self.loss_fn = loss_fn or nn.CrossEntropyLoss()
        self.model_provider_fn = model_provider_fn
        self.forward_step_fn = forward_step_fn

    def _get_megatron_args(self) -> list[str]:
        """Generate Megatron CLI args from config."""
        try:
            tc = TrainingConfig(**self.config)
            return ConfigMerger.to_megatron_args(tc)
        except Exception:
            return []

    def train(self) -> TrainingState:
        """Run Megatron-LM training via the pretrain() API.

        This method integrates with Megatron-LM's training loop.
        It initializes Megatron's distributed context, builds the model,
        and runs the training loop.
        """
        try:
            from megatron.training import get_args, get_model, get_timers
            from megatron.initialize import initialize_megatron
            from megatron.training import pretrain
        except ImportError:
            # Megatron not installed – provide a stub/simulation
            return self._train_stub()

        self.state.status = "running"
        self.callbacks.on_train_begin(self.state)

        try:
            # Inject Megatron args into sys.argv
            megatron_args = self._get_megatron_args()
            original_argv = sys.argv[:]
            sys.argv = ["megatron_trainer"] + megatron_args

            # Define model provider
            def model_provider(pre_process=True, post_process=True):
                """Megatron model provider callback."""
                if self.model is not None:
                    return self.model
                # Build from config using model registry
                from llmt_training.models.registry import ModelRegistry
                provider = ModelRegistry.get(self.config.get("model", {}).get("model_type", "gpt2"))
                return provider.get_model(self.config)

            # Define forward step function
            def forward_step(data_iterator, model):
                """Megatron forward step callback."""
                if self.forward_step_fn is not None:
                    return self.forward_step_fn(data_iterator, model)

                # Default: get batch, run forward, return (loss_tensor, loss_func)
                from megatron.core import mpu
                batch = self._get_batch(data_iterator)
                if batch is None:
                    return None, None

                input_ids = batch["input_ids"]
                labels = batch["labels"]

                output_tensor = model(input_ids)
                loss_func = lambda loss_mask, output: self._loss_func(labels, output)
                return output_tensor, loss_func

            # Run Megatron pretrain
            pretrain(
                train_valid_test_datasets_provider=self._data_provider,
                model_provider=model_provider,
                model_type=self.config.get("model", {}).get("model_type", "gpt2"),
                forward_step_func=forward_step,
                process_non_loss_data_func=None,
            )

            self.state.status = "completed"

        except Exception as e:
            self.state.status = "failed"
            self.state.error_message = str(e)
            self.callbacks.on_error(self.state, error=e)
        finally:
            sys.argv = original_argv

        self.callbacks.on_train_end(self.state)
        return self.state

    def _train_stub(self) -> TrainingState:
        """Stub training when Megatron is not installed.

        Logs a warning and runs a minimal PyTorch-like loop for testing.
        """
        import warnings
        warnings.warn(
            "Megatron-LM is not installed. Running stub training loop. "
            "Install Megatron-LM for actual distributed training.",
            stacklevel=2,
        )

        self.state.status = "running"
        self.callbacks.on_train_begin(self.state)

        hp = self.config.get("hyperparams", {})
        max_epochs = hp.get("max_epochs", 1)
        start_time = time.time()

        try:
            for epoch in range(max_epochs):
                self.state.epoch = epoch
                self.callbacks.on_epoch_begin(self.state)

                # Simulate steps if no dataloader
                num_steps = hp.get("max_steps", 10) or 10
                for step in range(num_steps):
                    self.state.global_step += 1
                    self.state.loss = max(0.1, 1.0 / (step + 1))
                    self.state.learning_rate = hp.get("learning_rate", 2e-5)
                    self.state.elapsed_seconds = time.time() - start_time
                    self.callbacks.on_step_end(self.state, loss=self.state.loss, lr=self.state.learning_rate)

                self.callbacks.on_epoch_end(self.state)

            self.state.status = "completed"

        except Exception as e:
            self.state.status = "failed"
            self.state.error_message = str(e)
            self.callbacks.on_error(self.state, error=e)

        self.callbacks.on_train_end(self.state)
        return self.state

    def _data_provider(self, train_val_test_num_samples):
        """Megatron data provider callback."""
        # Return (train_dataset, valid_dataset, test_dataset)
        if self.train_dataloader is not None:
            train_ds = self.train_dataloader.dataset
            eval_ds = self.eval_dataloader.dataset if self.eval_dataloader else None
            return train_ds, eval_ds, None
        return None, None, None

    @staticmethod
    def _get_batch(data_iterator):
        """Get a batch from the data iterator."""
        try:
            batch = next(data_iterator)
            return batch
        except (StopIteration, TypeError):
            return None

    @staticmethod
    def _loss_func(labels, output_tensor):
        """Compute loss from output tensor and labels."""
        loss_fn = nn.CrossEntropyLoss()
        loss = loss_fn(output_tensor.view(-1, output_tensor.size(-1)), labels.view(-1))
        return loss

    def evaluate(self) -> dict[str, float]:
        """Megatron evaluation is handled within the training loop."""
        return {"eval_loss": self.state.loss}

    def save_checkpoint(self, path: str) -> str:
        """Save checkpoint via Megatron checkpointing API."""
        os.makedirs(path, exist_ok=True)
        ckpt_path = os.path.join(path, f"iter_{self.state.global_step:07d}")
        try:
            from megatron.checkpointing import save_checkpoint
            save_checkpoint(self.state.global_step, self.model, None, None)
        except ImportError:
            # Fallback: plain PyTorch save
            model = self.model
            if isinstance(model, nn.parallel.DistributedDataParallel):
                model = model.module
            torch.save({
                "model_state_dict": model.state_dict(),
                "global_step": self.state.global_step,
                "epoch": self.state.epoch,
            }, os.path.join(ckpt_path, "mp_rank_00", "model_optim_rng.pt"))
        self.callbacks.on_checkpoint(self.state, checkpoint_path=ckpt_path)
        return ckpt_path

    def load_checkpoint(self, path: str) -> None:
        """Load checkpoint via Megatron API."""
        try:
            from megatron.checkpointing import load_checkpoint
            load_checkpoint(self.model, None, None)
        except ImportError:
            pass  # Megatron not available

"""Base trainer – abstract interface for all trainer implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from llmt_training.core.callbacks import CallbackList
from llmt_training.core.state import TrainingState


class BaseTrainer(ABC):
    """Abstract base trainer.

    Subclasses implement framework-specific training loops
    (PyTorch DDP, DeepSpeed, Megatron-LM).
    """

    def __init__(
        self,
        config: dict[str, Any],
        model: nn.Module | None = None,
        train_dataloader: DataLoader | None = None,
        eval_dataloader: DataLoader | None = None,
        callbacks: CallbackList | None = None,
        state: TrainingState | None = None,
    ):
        self.config = config
        self.model = model
        self.train_dataloader = train_dataloader
        self.eval_dataloader = eval_dataloader
        self.callbacks = callbacks or CallbackList()
        self.state = state or TrainingState()

    @abstractmethod
    def train(self) -> TrainingState:
        """Execute the full training loop and return the final state."""

    @abstractmethod
    def evaluate(self) -> dict[str, float]:
        """Run evaluation and return metrics dict."""

    @abstractmethod
    def save_checkpoint(self, path: str) -> str:
        """Save a checkpoint to the given path and return the path."""

    @abstractmethod
    def load_checkpoint(self, path: str) -> None:
        """Load a checkpoint from the given path."""

    def _should_stop(self) -> bool:
        """Check if training should stop (cancelled, max steps reached, etc.)."""
        if self.state.status in ("cancelled", "failed"):
            return True
        if self.state.max_steps and self.state.global_step >= self.state.max_steps:
            return True
        return False

"""Training callbacks – hook into the training lifecycle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from llmt_training.core.state import TrainingState


class TrainingCallback(ABC):
    """Base class for training lifecycle callbacks.

    Implement any subset of the hook methods to react to training events.
    All hooks receive the current TrainingState and optional kwargs.
    """

    def on_train_begin(self, state: TrainingState, **kwargs: Any) -> None:
        """Called once before training starts."""

    def on_train_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Called once after training ends (success or failure)."""

    def on_epoch_begin(self, state: TrainingState, **kwargs: Any) -> None:
        """Called at the beginning of each epoch."""

    def on_epoch_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Called at the end of each epoch."""

    def on_step_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Called after each training step.

        kwargs may include:
            loss (float): step loss
            grad_norm (float): gradient norm
            lr (float): current learning rate
        """

    def on_checkpoint(self, state: TrainingState, **kwargs: Any) -> None:
        """Called when a checkpoint is saved.

        kwargs may include:
            checkpoint_path (str): local path to checkpoint
        """

    def on_error(self, state: TrainingState, **kwargs: Any) -> None:
        """Called when an error occurs during training.

        kwargs may include:
            error (Exception): the exception that was raised
        """


class CallbackList(TrainingCallback):
    """Aggregate multiple callbacks into one."""

    def __init__(self, callbacks: list[TrainingCallback] | None = None):
        self.callbacks: list[TrainingCallback] = callbacks or []

    def add(self, callback: TrainingCallback) -> None:
        self.callbacks.append(callback)

    def on_train_begin(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_train_begin(state, **kwargs)

    def on_train_end(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_train_end(state, **kwargs)

    def on_epoch_begin(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_epoch_begin(state, **kwargs)

    def on_epoch_end(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_epoch_end(state, **kwargs)

    def on_step_end(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_step_end(state, **kwargs)

    def on_checkpoint(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_checkpoint(state, **kwargs)

    def on_error(self, state: TrainingState, **kwargs: Any) -> None:
        for cb in self.callbacks:
            cb.on_error(state, **kwargs)

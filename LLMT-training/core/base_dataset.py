"""Base dataset – abstract interface for training data loading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import torch
from torch.utils.data import Dataset


class BaseDataset(ABC, Dataset):
    """Abstract base class for training datasets.

    Subclasses implement data loading logic for different formats
    (JSONL, Parquet, Megatron bin/idx, NPY, etc.).
    """

    @abstractmethod
    def __len__(self) -> int:
        """Return the number of samples."""

    @abstractmethod
    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        """Return a single sample as a dict of tensors.

        Common keys:
            input_ids (Tensor[int]): Token IDs, shape (seq_length,)
            attention_mask (Tensor[int]): Mask, shape (seq_length,)
            labels (Tensor[int]): Target token IDs, shape (seq_length,)
        """

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict[str, Any]) -> "BaseDataset":
        """Construct a dataset instance from a training config dict.

        Args:
            config: TrainingConfig.model_dump() or equivalent dict.

        Returns:
            A ready-to-use dataset instance.
        """

    def get_collate_fn(self) -> Any | None:
        """Return a custom collate function for DataLoader, or None for default."""
        return None

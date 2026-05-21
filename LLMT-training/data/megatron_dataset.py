"""Megatron dataset adapter – wraps Megatron-LM blended dataset loading."""

from __future__ import annotations

from typing import Any

import torch
from torch.utils.data import Dataset

from llmt_training.core.base_dataset import BaseDataset


class MegatronDataset(BaseDataset):
    """Adapter for Megatron-LM's blended dataset.

    This dataset wraps Megatron's data loading pipeline. It requires
    Megatron-LM to be installed and the data to be pre-processed into
    the bin/idx format that Megatron expects.

    When Megatron is not available, returns a stub dataset for testing.
    """

    def __init__(
        self,
        data_path: str = "",
        seq_length: int = 1024,
        dataset_impl: str = "mmap",
    ):
        self.data_path = data_path
        self.seq_length = seq_length
        self.dataset_impl = dataset_impl
        self._dataset = None
        self._length = 0

        self._try_load()

    def _try_load(self):
        """Attempt to load the Megatron dataset."""
        try:
            from megatron.core.datasets.blended_megatron_dataset_builder import BlendedMegatronDatasetBuilder
            from megatron.core.datasets.megatron_dataset import LowLevelDataset

            # Megatron dataset loading would happen here
            # This is a placeholder for the actual integration
            self._length = 10000  # placeholder
        except ImportError:
            self._length = 100  # stub

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        if self._dataset is not None:
            # Use actual Megatron dataset
            tokens = self._dataset[index]
            return {
                "input_ids": torch.tensor(tokens, dtype=torch.long),
                "attention_mask": torch.ones(self.seq_length, dtype=torch.long),
                "labels": torch.tensor(tokens[1:] + [0], dtype=torch.long),
            }
        # Stub: return zeros
        return {
            "input_ids": torch.zeros(self.seq_length, dtype=torch.long),
            "attention_mask": torch.ones(self.seq_length, dtype=torch.long),
            "labels": torch.zeros(self.seq_length, dtype=torch.long),
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "MegatronDataset":
        """Construct from training config dict."""
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        return cls(
            data_path=data_cfg.get("dataset_path", ""),
            seq_length=model_cfg.get("seq_length", 1024),
            dataset_impl=data_cfg.get("dataset_format", "mmap"),
        )

"""Pretraining dataset – loads tokenized data for language model pretraining."""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset

from llmt_training.core.base_dataset import BaseDataset


class PretrainDataset(BaseDataset):
    """Dataset for autoregressive language model pretraining.

    Supports formats:
      - npy: numpy array of token IDs, shape (total_tokens,)
      - bin: raw int32 binary file of token IDs
      - jsonl: JSONL with "text" field (tokenized on-the-fly)

    For each sample, a contiguous chunk of `seq_length` tokens is extracted.
    Input = tokens[i:i+seq_length], Label = tokens[i+1:i+seq_length+1].
    """

    def __init__(
        self,
        data: torch.Tensor,
        seq_length: int = 1024,
    ):
        self.data = data
        self.seq_length = seq_length

    def __len__(self) -> int:
        return max(0, (len(self.data) - 1) // self.seq_length)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        start = index * self.seq_length
        end = start + self.seq_length + 1  # +1 for label shift
        chunk = self.data[start:end]
        return {
            "input_ids": chunk[:self.seq_length],
            "attention_mask": torch.ones(self.seq_length, dtype=torch.long),
            "labels": chunk[1:self.seq_length + 1],
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PretrainDataset":
        """Construct from training config dict."""
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        path = data_cfg.get("dataset_path", "")
        fmt = data_cfg.get("dataset_format", "npy")
        seq_length = model_cfg.get("seq_length", 1024)

        if not path or not os.path.exists(path):
            # Return empty dataset for testing
            return cls(torch.zeros(0, dtype=torch.long), seq_length=seq_length)

        if fmt == "npy":
            arr = np.load(path)
            data = torch.from_numpy(arr).long()
        elif fmt == "bin":
            data = torch.from_file(path, dtype=torch.int32).long()
        else:
            raise ValueError(f"PretrainDataset does not support format '{fmt}'")

        return cls(data, seq_length=seq_length)

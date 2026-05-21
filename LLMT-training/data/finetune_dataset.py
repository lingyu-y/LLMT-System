"""Fine-tuning dataset – loads JSONL data for supervised fine-tuning."""

from __future__ import annotations

import json
import os
from typing import Any

import torch
from torch.utils.data import Dataset

from llmt_training.core.base_dataset import BaseDataset


class FinetuneDataset(BaseDataset):
    """Dataset for supervised fine-tuning from JSONL files.

    Expected JSONL format per line:
      {"text": "prompt + completion text", ...}

    Tokenization is done on-the-fly using the provided tokenizer.
    If no tokenizer is given, raw text is included and must be tokenized
    in a collate function.
    """

    def __init__(
        self,
        samples: list[dict[str, Any]],
        seq_length: int = 512,
        tokenizer=None,
    ):
        self.samples = samples
        self.seq_length = seq_length
        self.tokenizer = tokenizer

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        sample = self.samples[index]
        text = sample.get("text", "")

        if self.tokenizer is not None:
            encoding = self.tokenizer(
                text,
                max_length=self.seq_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            input_ids = encoding["input_ids"].squeeze(0)
            attention_mask = encoding["attention_mask"].squeeze(0)
            labels = input_ids.clone()
            # Mask padding tokens in labels
            labels[labels == self.tokenizer.pad_token_id] = -100
        else:
            # Return raw text (collate_fn must handle tokenization)
            input_ids = torch.zeros(self.seq_length, dtype=torch.long)
            attention_mask = torch.zeros(self.seq_length, dtype=torch.long)
            labels = torch.full((self.seq_length,), -100, dtype=torch.long)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "FinetuneDataset":
        """Construct from training config dict."""
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        path = data_cfg.get("dataset_path", "")
        seq_length = model_cfg.get("seq_length", 512)

        samples: list[dict[str, Any]] = []
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        samples.append(json.loads(line))

        return cls(samples, seq_length=seq_length)

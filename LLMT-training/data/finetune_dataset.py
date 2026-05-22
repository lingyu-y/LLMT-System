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
            input_ids = encoding["input_ids"].squeeze(0).long()
            attention_mask = encoding["attention_mask"].squeeze(0).long()
            labels = input_ids.clone().long()
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
    def from_config(cls, config: dict[str, Any], tokenizer=None) -> "FinetuneDataset":
        """Construct from training config dict.

        Supports multiple file formats:
          - JSONL: one JSON object per line (each with a "text" field)
          - JSON array: a single JSON array of objects
          - Plain text: one sample per line (wrapped as {"text": line})
          - CSV: comma-separated, first column treated as text
        """
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        path = data_cfg.get("dataset_path", "")
        seq_length = model_cfg.get("seq_length", 512)

        samples: list[dict[str, Any]] = []
        if not path or not os.path.exists(path):
            return cls(samples, seq_length=seq_length)

        raw = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except UnicodeDecodeError:
            # Binary file – not suitable for fine-tuning text data
            return cls(samples, seq_length=seq_length)

        if not raw.strip():
            return cls(samples, seq_length=seq_length)

        # Try JSON array first (e.g. [{"text": "..."}, ...])
        stripped = raw.strip()
        if stripped.startswith("["):
            try:
                arr = json.loads(stripped)
                if isinstance(arr, list):
                    for item in arr:
                        if isinstance(item, dict):
                            samples.append(item)
                        elif isinstance(item, str):
                            samples.append({"text": item})
                    return cls(samples, seq_length=seq_length)
            except json.JSONDecodeError:
                pass  # Fall through to JSONL / plain text

        # Try JSONL (one JSON object per line)
        jsonl_ok = True
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    samples.append(obj)
                elif isinstance(obj, str):
                    samples.append({"text": obj})
                else:
                    jsonl_ok = False
                    break
            except json.JSONDecodeError:
                jsonl_ok = False
                break

        if jsonl_ok and samples:
            return cls(samples, seq_length=seq_length)

        # Fallback: treat as plain text (one sample per line or entire file)
        samples = []
        lines = [l.strip() for l in stripped.splitlines() if l.strip()]
        if len(lines) == 0:
            return cls(samples, seq_length=seq_length)
        elif len(lines) == 1:
            # Single block of text → one sample
            samples.append({"text": lines[0]})
        else:
            # Multiple lines → one sample per line
            # If it looks like CSV (first line has commas), try to parse
            if "," in lines[0] and len(lines) > 1:
                import csv
                import io
                reader = csv.reader(io.StringIO(stripped))
                for row in reader:
                    text = row[0] if row else ""
                    if text:
                        samples.append({"text": text})
            else:
                for line in lines:
                    samples.append({"text": line})

        return cls(samples, seq_length=seq_length)

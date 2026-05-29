"""Fine-tuning dataset – loads JSONL data for supervised fine-tuning."""

from __future__ import annotations

import bisect
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

        if self.tokenizer is not None:
            input_ids, attention_mask, labels = _encode_causal_sample(
                sample,
                self.tokenizer,
                self.seq_length,
            )
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

        When ``dataset_paths`` contains multiple files, each file is read
        and parsed independently before moving to the next, keeping peak
        memory bounded to a single file's raw content rather than all files.
        """
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        seq_length = model_cfg.get("seq_length", 512)

        paths: list[str] = list(data_cfg.get("dataset_paths") or [])
        single = data_cfg.get("dataset_path", "")
        if not paths and single:
            paths = [single]

        if len(paths) > 1:
            return ShardedFinetuneDataset(
                file_paths=paths,
                seq_length=seq_length,
                tokenizer=tokenizer,
            )

        print(f"[FinetuneDataset] 共 {len(paths)} 个数据文件:")
        for i, p in enumerate(paths):
            print(f"  [{i + 1}/{len(paths)}] {p}")

        samples: list[dict[str, Any]] = []
        for path in paths:
            if not path or not os.path.exists(path):
                print(f"[FinetuneDataset]   跳过（不存在）: {path}")
                continue
            file_samples = _parse_file_samples(path)
            print(f"[FinetuneDataset]   {os.path.basename(path)}: {len(file_samples)} 条样本")
            samples.extend(file_samples)

        print(f"[FinetuneDataset] 总样本数: {len(samples)}")
        return cls(samples, seq_length=seq_length, tokenizer=tokenizer)


def _parse_file_samples(path: str) -> list[dict[str, Any]]:
    """Parse a single data file into a list of sample dicts.

    Reads the file line-by-line for JSONL / text formats so peak memory
    is one line rather than the entire file content.  Falls back to full-file
    read only for JSON-array format.
    """
    samples: list[dict[str, Any]] = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline()
    except UnicodeDecodeError:
        return samples  # binary file – not suitable for text data

    if not first_line:
        return samples

    first_line = first_line.strip()

    # --- JSON array format (reads entire file) ---
    if first_line.startswith("["):
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.loads(f.read())
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict):
                        samples.append(item)
                    elif isinstance(item, str):
                        samples.append({"text": item})
            return samples
        except json.JSONDecodeError:
            pass  # Fall through to line-by-line

    # --- Line-by-line: JSONL or plain text ---
    # Re-open so we process every line including the first
    jsonl_lines = 0
    text_lines = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Try JSON decode first
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    samples.append(obj)
                    jsonl_lines += 1
                    continue
                elif isinstance(obj, str):
                    samples.append({"text": obj})
                    jsonl_lines += 1
                    continue
            except json.JSONDecodeError:
                pass

            # Fallback: plain text line
            samples.append({"text": line})
            text_lines += 1

    # If most lines were JSON, keep those; otherwise all plain-text samples
    # are fine too.
    return samples


def _count_jsonl_lines(path: str) -> int:
    """Count non-empty JSONL lines without loading the full file into memory."""
    count = 0
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1048576)
                if not chunk:
                    break
                count += chunk.count(b"\n")
    except OSError:
        return 0
    return count


class ShardedFinetuneDataset(BaseDataset):
    """Dataset that loads JSONL shards lazily — only one shard in memory at a time.

    Designed for sharded preprocessed data (``data_shard_*.jsonl``).
    Pre-scans line counts for ``__len__`` so ``random_split`` /
    ``DistributedSampler`` work without loading all samples.
    """

    def __init__(
        self,
        file_paths: list[str],
        seq_length: int = 512,
        tokenizer=None,
    ):
        self.file_paths = sorted(file_paths)
        self.seq_length = seq_length
        self.tokenizer = tokenizer

        self._file_sample_counts: list[int] = []
        self._offsets: list[int] = [0]
        for p in self.file_paths:
            n = _count_jsonl_lines(p)
            self._file_sample_counts.append(n)
            self._offsets.append(self._offsets[-1] + n)

        self._total_samples = self._offsets[-1]

        self._loaded_idx: int = -1
        self._loaded_samples: list[dict[str, Any]] | None = None

        print(f"[ShardedFinetuneDataset] {len(self.file_paths)} 个分片文件:")
        for i, p in enumerate(self.file_paths):
            print(f"  [{i + 1}/{len(self.file_paths)}] {os.path.basename(p)}: {self._file_sample_counts[i]} 条样本")
        print(f"[ShardedFinetuneDataset] 总样本数: {self._total_samples}")

    def __len__(self) -> int:
        return self._total_samples

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        file_idx = bisect.bisect_right(self._offsets, index) - 1
        file_idx = max(0, min(file_idx, len(self.file_paths) - 1))
        local_idx = index - self._offsets[file_idx]

        self._ensure_loaded(file_idx)

        local_idx = min(local_idx, len(self._loaded_samples) - 1)
        sample = self._loaded_samples[local_idx]

        if self.tokenizer is not None:
            input_ids, attention_mask, labels = _encode_causal_sample(
                sample,
                self.tokenizer,
                self.seq_length,
            )
        else:
            input_ids = torch.zeros(self.seq_length, dtype=torch.long)
            attention_mask = torch.zeros(self.seq_length, dtype=torch.long)
            labels = torch.full((self.seq_length,), -100, dtype=torch.long)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }

    def _ensure_loaded(self, file_idx: int) -> None:
        """Load shard *file_idx* and drop the previously cached one."""
        if self._loaded_idx == file_idx:
            return
        self._loaded_samples = _parse_file_samples(self.file_paths[file_idx])
        self._loaded_idx = file_idx
        actual = len(self._loaded_samples)
        if actual != self._file_sample_counts[file_idx]:
            self._file_sample_counts[file_idx] = actual
            self._offsets = [0]
            for c in self._file_sample_counts:
                self._offsets.append(self._offsets[-1] + c)
            self._total_samples = self._offsets[-1]

    @classmethod
    def from_config(cls, config: dict[str, Any], tokenizer=None) -> "ShardedFinetuneDataset":
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        paths: list[str] = list(data_cfg.get("dataset_paths") or [])
        single = data_cfg.get("dataset_path", "")
        if not paths and single:
            paths = [single]
        return cls(
            file_paths=paths,
            seq_length=model_cfg.get("seq_length", 512),
            tokenizer=tokenizer,
        )


_PROMPT_KEYS = ("prompt", "instruction", "question", "input")
_RESPONSE_KEYS = ("response", "completion", "answer", "output")


def _first_text(sample: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = sample.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _build_sample_text(sample: dict[str, Any]) -> tuple[str, str | None]:
    prompt = _first_text(sample, _PROMPT_KEYS)
    response = _first_text(sample, _RESPONSE_KEYS)
    if prompt and response:
        prompt_part = f"{prompt}\n"
        return f"{prompt_part}{response}", prompt_part

    text = str(sample.get("text", "")).strip()
    return text, None


def _tokenize_1d(
    tokenizer,
    text: str,
    max_length: int,
    padding: str | bool | None = False,
    truncation: bool = True,
) -> tuple[torch.Tensor, torch.Tensor]:
    kwargs: dict[str, Any] = {
        "max_length": max_length,
        "truncation": truncation,
        "return_tensors": "pt",
    }
    if padding:
        kwargs["padding"] = padding
    encoding = tokenizer(
        text,
        **kwargs,
    )
    return encoding["input_ids"].squeeze(0).long(), encoding["attention_mask"].squeeze(0).long()


def _pad_to_length(values: torch.Tensor, length: int, pad_value: int) -> torch.Tensor:
    if values.numel() >= length:
        return values[:length]
    pad = torch.full((length - values.numel(),), pad_value, dtype=values.dtype)
    return torch.cat([values, pad], dim=0)


def _encode_causal_sample(
    sample: dict[str, Any],
    tokenizer,
    seq_length: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    text, prompt_part = _build_sample_text(sample)
    pad_id = int(getattr(tokenizer, "pad_token_id", 0) or 0)

    token_ids, token_mask = _tokenize_1d(
        tokenizer,
        text,
        max_length=seq_length + 1,
        padding=None,
        truncation=True,
    )

    input_ids = _pad_to_length(token_ids[:-1], seq_length, pad_id)
    attention_mask = _pad_to_length(token_mask[:-1], seq_length, 0)
    labels = _pad_to_length(token_ids[1:], seq_length, -100)

    input_ids[input_ids < 0] = pad_id
    labels[attention_mask == 0] = -100
    labels[labels == pad_id] = -100

    if prompt_part is not None:
        prompt_ids, _ = _tokenize_1d(
            tokenizer,
            prompt_part,
            max_length=seq_length + 1,
            padding=None,
            truncation=True,
        )
        prompt_label_cutoff = max(min(prompt_ids.numel(), seq_length) - 1, 0)
        if prompt_label_cutoff:
            labels[:prompt_label_cutoff] = -100

    return input_ids.long(), attention_mask.long(), labels.long()

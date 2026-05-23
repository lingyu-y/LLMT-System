"""Pretraining dataset – loads tokenized data for language model pretraining.

Supports single-file and multi-file mode.  In multi-file mode data files
are loaded **one at a time** so only a single file's worth of tokens
resides in GPU-accessible RAM at any moment.
"""

from __future__ import annotations

import bisect
import os
from typing import Any

import numpy as np
import torch

from llmt_training.core.base_dataset import BaseDataset


# ---------------------------------------------------------------------------
# Single-file dataset (original behaviour, kept for backward compatibility)
# ---------------------------------------------------------------------------

class PretrainDataset(BaseDataset):
    """Single-file autoregressive pretraining dataset.

    Supports formats:
      - npy: numpy array of token IDs, shape (total_tokens,)
      - bin: raw int32 binary file of token IDs
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
        end = start + self.seq_length + 1
        chunk = self.data[start:end]
        return {
            "input_ids": chunk[:self.seq_length],
            "attention_mask": torch.ones(self.seq_length, dtype=torch.long),
            "labels": chunk[1:self.seq_length + 1],
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "BaseDataset":
        """Construct from training config dict.

        If ``dataset_paths`` contains >1 entry a :class:`ConcatPretrainDataset`
        is returned so files are consumed one at a time.
        """
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        fmt = data_cfg.get("dataset_format", "npy")
        seq_length = model_cfg.get("seq_length", 1024)
        paths = data_cfg.get("dataset_paths") or []
        single = data_cfg.get("dataset_path", "")

        # Normalise: build the effective list of data files
        if paths and len(paths) > 1:
            return ConcatPretrainDataset(paths, seq_length=seq_length, fmt=fmt)
        if paths:
            single = single or paths[0]

        if not single or not os.path.exists(single):
            return cls(torch.zeros(0, dtype=torch.long), seq_length=seq_length)

        print(f"[PretrainDataset] 单文件模式: {single}")
        return cls(_load_single_file(single, fmt), seq_length=seq_length)


# ---------------------------------------------------------------------------
# Multi-file dataset – lazy-loads one file at a time
# ---------------------------------------------------------------------------

class ConcatPretrainDataset(BaseDataset):
    """Dataset that concatenates multiple data files *logically* while keeping
    only one file's tensor in memory at a time.

    File sizes are pre-scanned via memory-mapped reads (zero-copy) so the
    total number of samples is known upfront, which keeps
    ``random_split`` / ``DistributedSampler`` working correctly.
    """

    def __init__(self, file_paths: list[str], seq_length: int = 1024, fmt: str = "npy"):
        self.file_paths = sorted(file_paths)
        self.seq_length = seq_length
        self.fmt = fmt

        print(f"[PretrainDataset] 多文件模式，共 {len(self.file_paths)} 个文件:")
        for i, p in enumerate(self.file_paths):
            print(f"  [{i + 1}/{len(self.file_paths)}] {p}")

        # Pre-scan file sizes (mmap – no data loaded into RAM)
        self._file_sizes: list[int] = []
        self._offsets: list[int] = [0]  # cumulative *token* offsets
        for p in self.file_paths:
            sz = _probe_file_length(p)
            self._file_sizes.append(sz)
            self._offsets.append(self._offsets[-1] + sz)
            print(f"  [PretrainDataset]   tokens={sz:,}  path={os.path.basename(p)}")

        self._total_tokens = self._offsets[-1]
        print(f"[PretrainDataset] 总 tokens={self._total_tokens:,}, 样本数={len(self)}")

        # Lazy cache – only the *currently needed* file is in RAM
        self._loaded_idx: int = -1
        self._loaded_data: torch.Tensor | None = None

    # -- len ----------------------------------------------------------------

    def __len__(self) -> int:
        return max(0, (self._total_tokens - 1) // self.seq_length)

    # -- getitem ------------------------------------------------------------

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        token_start = index * self.seq_length
        need = self.seq_length + 1  # +1 for label shift

        # Locate the file that contains *token_start*
        file_idx = bisect.bisect_right(self._offsets, token_start) - 1
        file_idx = max(0, min(file_idx, len(self.file_paths) - 1))
        file_end_token = self._offsets[file_idx + 1]

        # If the sample would straddle a file boundary, clamp to file end
        if token_start + need > file_end_token:
            token_start = max(0, file_end_token - need)

        self._ensure_loaded(file_idx)

        local_start = token_start - self._offsets[file_idx]
        local_end = local_start + need

        chunk = self._loaded_data[local_start:local_end]  # type: ignore[index]
        return {
            "input_ids": chunk[:self.seq_length],
            "attention_mask": torch.ones(self.seq_length, dtype=torch.long),
            "labels": chunk[1:need],
        }

    # -- helpers ------------------------------------------------------------

    def _ensure_loaded(self, file_idx: int) -> None:
        """Load *file_idx* into ``self._loaded_data``, dropping any previously
        cached file so memory stays bounded to a single file."""
        if self._loaded_idx == file_idx:
            return
        self._loaded_data = _load_single_file(self.file_paths[file_idx], self.fmt)
        self._loaded_idx = file_idx

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ConcatPretrainDataset":
        """Alternate constructor (used when routing via factory)."""
        data_cfg = config.get("data", {})
        model_cfg = config.get("model", {})
        return cls(
            file_paths=data_cfg.get("dataset_paths", []),
            seq_length=model_cfg.get("seq_length", 1024),
            fmt=data_cfg.get("dataset_format", "npy"),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _probe_file_length(path: str) -> int:
    """Return number of tokens in *path* without loading data into RAM."""
    try:
        arr = np.load(path, mmap_mode="r")
        return len(arr)
    except Exception:
        if path.endswith(".bin"):
            st = os.stat(path)
            return st.st_size // 4  # int32
        return 0


def _load_single_file(path: str, fmt: str) -> torch.Tensor:
    """Load a single data file into a ``torch.Tensor``."""
    if fmt in ("npy",):
        arr = np.load(path)
        return torch.from_numpy(arr).long()
    if fmt == "bin":
        return torch.from_file(path, dtype=torch.int32).long()
    raise ValueError(f"PretrainDataset does not support format '{fmt}'")

"""Batch validation helpers for trainer input safety."""

from __future__ import annotations

from typing import Any

import torch


def model_vocab_size(model: torch.nn.Module, config: dict[str, Any]) -> int | None:
    """Resolve the vocabulary size used by the model output head."""
    module = getattr(model, "module", model)
    try:
        return int(module.wte.weight.shape[0])
    except AttributeError:
        pass

    cfg_vocab = config.get("model", {}).get("vocab_size")
    if isinstance(cfg_vocab, int) and cfg_vocab > 0:
        return cfg_vocab
    return None


def validate_token_batch(
    batch: dict[str, Any],
    *,
    vocab_size: int | None,
    step: int,
) -> None:
    """Fail early when token IDs or labels would index outside vocab_size."""
    if vocab_size is None:
        return

    input_ids = batch.get("input_ids")
    if isinstance(input_ids, torch.Tensor) and input_ids.numel() > 0:
        min_id = int(input_ids.min().item())
        max_id = int(input_ids.max().item())
        if min_id < 0 or max_id >= vocab_size:
            hint = (
                "input_ids 中出现负数，通常是 labels 的 -100 mask 混入了模型输入。"
                if min_id < 0 else
                "请检查 tokenizer 与模型 vocab_size 是否一致。"
            )
            raise ValueError(
                "Token ID out of range before model forward: "
                f"step={step}, input_ids.min={min_id}, input_ids.max={max_id}, "
                f"model.vocab_size={vocab_size}. "
                f"{hint}"
            )

    labels = batch.get("labels")
    if isinstance(labels, torch.Tensor) and labels.numel() > 0:
        valid_labels = labels[labels != -100]
        if valid_labels.numel() == 0:
            return
        min_label = int(valid_labels.min().item())
        max_label = int(valid_labels.max().item())
        if min_label < 0 or max_label >= vocab_size:
            raise ValueError(
                "Label ID out of range before loss: "
                f"step={step}, labels.min={min_label}, labels.max={max_label}, "
                f"model.vocab_size={vocab_size}. "
                "labels 只能是 -100 或 [0, vocab_size) 范围内的 token id。"
            )


def sanitize_token_batch(
    batch: dict[str, Any],
    *,
    pad_token_id: int = 0,
) -> None:
    """Normalize token tensors in-place before validation and model forward."""
    input_ids = batch.get("input_ids")
    if isinstance(input_ids, torch.Tensor) and input_ids.numel() > 0:
        if bool((input_ids < 0).any().item()):
            input_ids = input_ids.clone()
            input_ids[input_ids < 0] = pad_token_id
            batch["input_ids"] = input_ids

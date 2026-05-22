"""Minimal fallback tokenizer for offline training and testing."""

from __future__ import annotations

from typing import Any

import torch


class SimpleTokenizer:
    """A simple whitespace-based tokenizer that produces integer ids.

    This tokenizer is only intended as a fallback when a pretrained
    HuggingFace tokenizer cannot be loaded from the cache or network.
    """

    def __init__(self, vocab_size: int = 50257, pad_token_id: int = 0, unk_token_id: int = 1) -> None:
        self.vocab_size = vocab_size
        self.pad_token_id = pad_token_id
        self.unk_token_id = unk_token_id

    def __call__(
        self,
        text: str,
        max_length: int | None = None,
        padding: str | None = None,
        truncation: bool = False,
        return_tensors: str | None = None,
        **kwargs: Any,
    ) -> dict[str, torch.Tensor] | dict[str, Any]:
        if max_length is None:
            max_length = len(text.split()) or 1

        token_strings = [token for token in text.split() if token]
        token_ids: list[int] = []
        for token in token_strings:
            idx = abs(hash(token)) % self.vocab_size
            if idx == self.pad_token_id:
                idx = self.unk_token_id
            token_ids.append(idx)

        if truncation and len(token_ids) > max_length:
            token_ids = token_ids[:max_length]

        if padding == "max_length":
            attention_mask = [1] * len(token_ids) + [0] * max(0, max_length - len(token_ids))
            token_ids = token_ids + [self.pad_token_id] * max(0, max_length - len(token_ids))
        else:
            attention_mask = [1] * len(token_ids)

        if not token_ids:
            token_ids = [self.pad_token_id] * max_length
            attention_mask = [0] * max_length

        output = {
            "input_ids": torch.tensor([token_ids], dtype=torch.long),
            "attention_mask": torch.tensor([attention_mask], dtype=torch.long),
        }
        if return_tensors == "pt":
            return output
        return {
            "input_ids": token_ids,
            "attention_mask": attention_mask,
        }

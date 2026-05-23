"""Minimal fallback tokenizer for offline training and testing.

Uses deterministic hash-based encoding (hashlib.md5) with a
bidirectional vocabulary that can be saved/loaded alongside
model checkpoints.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import torch


def _deterministic_hash(token: str) -> int:
    """Return a deterministic hash for a token (consistent across processes)."""
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest, 16)


class SimpleTokenizer:
    """A whitespace-based tokenizer with deterministic hash-based encoding.

    Maintains bidirectional vocabulary so that decode() can return
    human-readable text. The vocabulary is built during training and
    persisted alongside checkpoints.

    During encoding, previously-seen tokens are looked up in the
    vocabulary first. New tokens are assigned via deterministic hash.
    """

    def __init__(self, vocab_size: int = 50257, pad_token_id: int = 0, unk_token_id: int = 1) -> None:
        self.vocab_size = vocab_size
        self.pad_token_id = pad_token_id
        self.unk_token_id = unk_token_id
        self.word_to_id: dict[str, int] = {}
        self.id_to_word: dict[int, str] = {}

    def __call__(
        self,
        text: str | list[str],
        max_length: int | None = None,
        padding: str | None = None,
        truncation: bool = False,
        return_tensors: str | None = None,
        **kwargs: Any,
    ) -> dict[str, torch.Tensor] | dict[str, Any]:
        if isinstance(text, list):
            return self._batch_encode(text, max_length, padding, truncation, return_tensors, **kwargs)

        if max_length is None:
            max_length = len(text.split()) or 1

        token_strings = [token for token in text.split() if token]
        token_ids: list[int] = []
        for token in token_strings:
            idx = self._encode_token(token)
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

    def _batch_encode(
        self,
        texts: list[str],
        max_length: int | None = None,
        padding: str | None = None,
        truncation: bool = False,
        return_tensors: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        all_ids = []
        all_masks = []
        if max_length is None:
            max_length = max((len(t.split()) for t in texts), default=1)

        for text in texts:
            result = self(text, max_length=max_length, padding=padding,
                          truncation=truncation, return_tensors=None, **kwargs)
            all_ids.append(result["input_ids"])
            all_masks.append(result["attention_mask"])

        return {
            "input_ids": torch.tensor(all_ids, dtype=torch.long),
            "attention_mask": torch.tensor(all_masks, dtype=torch.long),
        }

    def _encode_token(self, token: str) -> int:
        # Known token: return its saved ID
        if token in self.word_to_id:
            return self.word_to_id[token]

        # New token: assign via deterministic hash
        idx = _deterministic_hash(token) % self.vocab_size
        if idx == self.pad_token_id:
            idx = self.unk_token_id
        self.word_to_id[token] = idx
        self.id_to_word[idx] = token
        return idx

    def decode(self, token_ids, skip_special_tokens: bool = False, **kwargs) -> str:
        """Decode token IDs back to text using the reverse vocabulary."""
        if isinstance(token_ids, torch.Tensor):
            token_ids = token_ids.tolist()
        words: list[str] = []
        for t in token_ids:
            if skip_special_tokens and t == self.pad_token_id:
                continue
            words.append(self.id_to_word.get(t, str(t)))
        return "".join(words) if words else ""

    @property
    def eos_token_id(self) -> int | None:
        return None

    @property
    def bos_token_id(self) -> int | None:
        return None

    # --- Persistence ---

    def save_vocab(self, path: str) -> None:
        """Save the bidirectional vocabulary to a JSON file."""
        serializable = {str(k): v for k, v in self.id_to_word.items()}
        word_to_id_serializable = {k: v for k, v in self.word_to_id.items()}
        meta = {
            "vocab_size": self.vocab_size,
            "pad_token_id": self.pad_token_id,
            "unk_token_id": self.unk_token_id,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "meta": meta,
                "id_to_word": serializable,
                "word_to_id": word_to_id_serializable,
            }, f, ensure_ascii=False)

    @classmethod
    def load_vocab(cls, path: str) -> "SimpleTokenizer":
        """Load a SimpleTokenizer from a vocab JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data["meta"]
        tokenizer = cls(
            vocab_size=meta["vocab_size"],
            pad_token_id=meta["pad_token_id"],
            unk_token_id=meta["unk_token_id"],
        )
        tokenizer.id_to_word = {int(k): v for k, v in data.get("id_to_word", {}).items()}
        # Pre-populate word_to_id as the inverse of id_to_word
        tokenizer.word_to_id = {v: int(k) for k, v in data.get("id_to_word", {}).items()}
        # Also load explicit word_to_id if present (for forward compatibility)
        if "word_to_id" in data:
            tokenizer.word_to_id.update(data["word_to_id"])
        return tokenizer

    def build_vocab_from_texts(self, texts: list[str]) -> None:
        """Build bidirectional vocabulary by encoding a list of texts."""
        for text in texts:
            for token in text.split():
                if token:
                    self._encode_token(token)

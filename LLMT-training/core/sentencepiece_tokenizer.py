"""SentencePiece tokenizer wrapper with a HuggingFace-like call interface."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

import torch


class SentencePieceTokenizer:
    """Thin wrapper around sentencepiece.SentencePieceProcessor."""

    def __init__(self, model_file: str):
        try:
            import sentencepiece as spm
        except ImportError as exc:
            raise RuntimeError("sentencepiece is required for SentencePieceTokenizer") from exc

        if not os.path.isfile(model_file):
            raise FileNotFoundError(f"SentencePiece model not found: {model_file}")

        self.model_file = os.path.abspath(model_file)
        self.processor = spm.SentencePieceProcessor(model_file=self.model_file)
        self.vocab_size = int(self.processor.get_piece_size())
        self.pad_token_id = self._id_or_default("pad_id", 0)
        self.unk_token_id = self._id_or_default("unk_id", 1)
        self.bos_token_id = self._id_or_none("bos_id")
        self.eos_token_id = self._id_or_none("eos_id")

    def _id_or_default(self, method_name: str, default: int) -> int:
        method = getattr(self.processor, method_name, None)
        if method is None:
            return default
        value = int(method())
        return value if value >= 0 else default

    def _id_or_none(self, method_name: str) -> int | None:
        method = getattr(self.processor, method_name, None)
        if method is None:
            return None
        value = int(method())
        return value if value >= 0 else None

    def __call__(
        self,
        text: str | list[str],
        max_length: int | None = None,
        padding: str | bool | None = False,
        truncation: bool = False,
        return_tensors: str | None = None,
        **kwargs: Any,
    ) -> dict[str, torch.Tensor] | dict[str, Any]:
        if isinstance(text, list):
            return self._batch_encode(text, max_length, padding, truncation, return_tensors)

        ids = list(self.processor.encode(text or "", out_type=int))
        if max_length is not None and truncation and len(ids) > max_length:
            ids = ids[:max_length]

        target_length = max_length if padding == "max_length" and max_length is not None else len(ids)
        attention_mask = [1] * len(ids)
        if target_length > len(ids):
            pad_count = target_length - len(ids)
            ids = ids + [self.pad_token_id] * pad_count
            attention_mask = attention_mask + [0] * pad_count

        if not ids:
            ids = [self.pad_token_id]
            attention_mask = [0]

        if return_tensors == "pt":
            return {
                "input_ids": torch.tensor([ids], dtype=torch.long),
                "attention_mask": torch.tensor([attention_mask], dtype=torch.long),
            }
        return {"input_ids": ids, "attention_mask": attention_mask}

    def _batch_encode(
        self,
        texts: list[str],
        max_length: int | None,
        padding: str | bool | None,
        truncation: bool,
        return_tensors: str | None,
    ) -> dict[str, torch.Tensor] | dict[str, Any]:
        encoded = [
            self(t, max_length=max_length, padding=False, truncation=truncation, return_tensors=None)
            for t in texts
        ]
        if padding in (True, "longest"):
            target_length = max((len(e["input_ids"]) for e in encoded), default=1)
        elif padding == "max_length" and max_length is not None:
            target_length = max_length
        else:
            target_length = None

        all_ids = []
        all_masks = []
        for item in encoded:
            ids = list(item["input_ids"])
            mask = list(item["attention_mask"])
            if target_length is not None and len(ids) < target_length:
                pad_count = target_length - len(ids)
                ids += [self.pad_token_id] * pad_count
                mask += [0] * pad_count
            all_ids.append(ids)
            all_masks.append(mask)

        if return_tensors == "pt":
            return {
                "input_ids": torch.tensor(all_ids, dtype=torch.long),
                "attention_mask": torch.tensor(all_masks, dtype=torch.long),
            }
        return {"input_ids": all_ids, "attention_mask": all_masks}

    def decode(self, token_ids, skip_special_tokens: bool = False, **kwargs) -> str:
        if isinstance(token_ids, torch.Tensor):
            token_ids = token_ids.tolist()
        ids = [int(i) for i in token_ids]
        if skip_special_tokens:
            special_ids = {self.pad_token_id, self.unk_token_id}
            if self.bos_token_id is not None:
                special_ids.add(self.bos_token_id)
            if self.eos_token_id is not None:
                special_ids.add(self.eos_token_id)
            ids = [i for i in ids if i not in special_ids]
        return self.processor.decode(ids)

    def save_pretrained(self, save_directory: str) -> None:
        os.makedirs(save_directory, exist_ok=True)
        shutil.copyfile(self.model_file, os.path.join(save_directory, "sentencepiece.model"))
        with open(os.path.join(save_directory, "tokenizer_config.json"), "w", encoding="utf-8") as f:
            json.dump({"tokenizer_type": "sentencepiece"}, f, ensure_ascii=False, indent=2)

    @classmethod
    def from_pretrained(cls, directory: str) -> "SentencePieceTokenizer":
        return cls(os.path.join(directory, "sentencepiece.model"))

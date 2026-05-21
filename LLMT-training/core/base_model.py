"""Base model provider – abstract interface for model construction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import torch
import torch.nn as nn


class BaseModelProvider(ABC):
    """Provides model, tokenizer, and loss function for training.

    Subclasses implement model-specific logic (GPT, BERT, LLaMA, etc.).
    """

    @abstractmethod
    def get_model(self, config: dict[str, Any]) -> nn.Module:
        """Build and return the model instance.

        Args:
            config: TrainingConfig.model_dump() or equivalent dict.

        Returns:
            nn.Module ready for training.
        """

    @abstractmethod
    def get_tokenizer(self, config: dict[str, Any]) -> Any:
        """Return the tokenizer associated with this model.

        Returns:
            A tokenizer object (HuggingFace PreTrainedTokenizer or equivalent).
        """

    @abstractmethod
    def get_loss_fn(self, config: dict[str, Any]) -> nn.Module:
        """Return the loss function for this model.

        Returns:
            A callable nn.Module that computes loss from (logits, labels).
        """

    def get_model_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return model-specific kwargs passed to the model constructor.

        Override to customize model initialization parameters.
        """
        return {
            "vocab_size": config.get("vocab_size", 50257),
            "hidden_size": config.get("hidden_size", 768),
            "num_layers": config.get("num_layers", 12),
            "num_attention_heads": config.get("num_attention_heads", 12),
            "seq_length": config.get("seq_length", 1024),
        }

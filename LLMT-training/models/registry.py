"""Model registry – maps model type names to provider classes."""

from __future__ import annotations

from typing import Any

from llmt_training.core.base_model import BaseModelProvider


_REGISTRY: dict[str, type[BaseModelProvider]] = {}


def _auto_register():
    """Register built-in model providers."""
    if _REGISTRY:
        return
    from llmt_training.models.gpt_provider import GPTModelProvider
    from llmt_training.models.bert_provider import BERTModelProvider

    _REGISTRY["gpt2"] = GPTModelProvider
    _REGISTRY["gpt"] = GPTModelProvider
    _REGISTRY["bert"] = BERTModelProvider
    _REGISTRY["bert-base"] = BERTModelProvider
    _REGISTRY["bert-large"] = BERTModelProvider


class ModelRegistry:
    """Static registry for model providers."""

    @staticmethod
    def get(model_type: str) -> BaseModelProvider:
        """Get a model provider instance by type name."""
        _auto_register()
        provider_cls = _REGISTRY.get(model_type)
        if provider_cls is None:
            available = ", ".join(sorted(_REGISTRY.keys()))
            raise ValueError(
                f"Unknown model type '{model_type}'. Available: {available}"
            )
        return provider_cls()

    @staticmethod
    def register(model_type: str, provider_cls: type[BaseModelProvider]) -> None:
        """Register a custom model provider."""
        _REGISTRY[model_type] = provider_cls

    @staticmethod
    def list_models() -> list[str]:
        """List all registered model type names."""
        _auto_register()
        return sorted(_REGISTRY.keys())

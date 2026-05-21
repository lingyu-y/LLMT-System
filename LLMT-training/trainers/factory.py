"""Trainer factory – selects the right trainer based on training strategy."""

from __future__ import annotations

from typing import Any

from llmt_training.core.base_trainer import BaseTrainer


def create_trainer(
    framework: str,
    parallel_strategy: str,
    config: dict[str, Any],
    **kwargs: Any,
) -> BaseTrainer:
    """Create a trainer instance based on framework and parallel strategy.

    Args:
        framework: "pytorch", "deepspeed", or "megatron"
        parallel_strategy: "ddp", "zero1", "zero2", "zero3", "zero3_offload",
                           "tp", "pp", "3d"
        config: Full training config dict
        **kwargs: Additional arguments passed to the trainer constructor

    Returns:
        A BaseTrainer subclass instance.

    Raises:
        ValueError: If framework/strategy combination is unsupported.
    """
    if framework == "pytorch":
        if parallel_strategy not in ("ddp",):
            raise ValueError(
                f"PyTorch framework only supports 'ddp' strategy, got '{parallel_strategy}'"
            )
        from llmt_training.trainers.pytorch_trainer import PyTorchTrainer
        return PyTorchTrainer(config=config, **kwargs)

    elif framework == "deepspeed":
        if parallel_strategy not in ("ddp", "zero1", "zero2", "zero3", "zero3_offload"):
            raise ValueError(
                f"DeepSpeed framework supports 'ddp', 'zero1', 'zero2', 'zero3', "
                f"'zero3_offload' strategies, got '{parallel_strategy}'"
            )
        from llmt_training.trainers.deepspeed_trainer import DeepSpeedTrainer
        return DeepSpeedTrainer(config=config, **kwargs)

    elif framework == "megatron":
        if parallel_strategy not in ("tp", "pp", "3d", "ddp", "zero1", "zero2", "zero3"):
            raise ValueError(
                f"Megatron framework supports 'tp', 'pp', '3d', 'ddp', "
                f"'zero1', 'zero2', 'zero3' strategies, got '{parallel_strategy}'"
            )
        from llmt_training.trainers.megatron_trainer import MegatronTrainer
        return MegatronTrainer(config=config, **kwargs)

    else:
        raise ValueError(f"Unsupported framework: {framework}")

"""Launcher factory – selects the right launcher based on framework/strategy."""

from __future__ import annotations

from typing import Any

from llmt_training.launcher.base_launcher import BaseLauncher


def create_launcher(
    framework: str,
    parallel_strategy: str,
    config: dict[str, Any],
) -> BaseLauncher:
    """Create a launcher instance based on framework and parallel strategy.

    Args:
        framework: "pytorch", "deepspeed", or "megatron"
        parallel_strategy: The parallelism strategy string
        config: Full training config dict

    Returns:
        A BaseLauncher subclass instance.
    """
    if framework == "pytorch":
        from llmt_training.launcher.torchrun_launcher import TorchrunLauncher
        return TorchrunLauncher(config)

    elif framework == "deepspeed":
        from llmt_training.launcher.deepspeed_launcher import DeepSpeedLauncher
        return DeepSpeedLauncher(config)

    elif framework == "megatron":
        from llmt_training.launcher.megatron_launcher import MegatronLauncher
        return MegatronLauncher(config)

    else:
        raise ValueError(f"Unsupported framework for launcher: {framework}")

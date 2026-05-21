"""Base launcher – abstract interface for distributed training launchers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLauncher(ABC):
    """Abstract base for launching distributed training jobs.

    A launcher is responsible for spawning the training process(es)
    with the correct distributed backend configuration.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def launch(self, trainer_script: str, **kwargs: Any) -> int:
        """Launch the training job.

        Args:
            trainer_script: Path to the Python training script to execute.
            **kwargs: Additional arguments.

        Returns:
            Process exit code (0 = success).
        """

    @abstractmethod
    def build_command(self, trainer_script: str, **kwargs: Any) -> list[str]:
        """Build the command-line invocation for the training job.

        Returns:
            List of command-line strings.
        """

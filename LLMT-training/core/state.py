"""Training state – shared mutable state tracked during training."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrainingState:
    """Tracks the current state of a training run."""

    task_code: str = ""
    status: str = "created"  # created | queued | running | completed | failed | cancelled

    # Progress
    epoch: int = 0
    global_step: int = 0
    max_epochs: int = 0
    max_steps: int | None = None

    # Metrics (latest values)
    loss: float = 0.0
    learning_rate: float = 0.0
    grad_norm: float = 0.0
    throughput: float = 0.0  # samples/sec

    # GPU metrics
    gpu_memory_used_mb: float = 0.0
    gpu_memory_total_mb: float = 0.0
    gpu_utilization_pct: float = 0.0

    # Timing
    elapsed_seconds: float = 0.0

    # Custom metrics
    custom_metrics: dict[str, Any] = field(default_factory=dict)

    # Error
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_code": self.task_code,
            "status": self.status,
            "epoch": self.epoch,
            "global_step": self.global_step,
            "loss": self.loss,
            "learning_rate": self.learning_rate,
            "grad_norm": self.grad_norm,
            "throughput": self.throughput,
            "gpu_memory_used_mb": self.gpu_memory_used_mb,
            "gpu_memory_total_mb": self.gpu_memory_total_mb,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "elapsed_seconds": self.elapsed_seconds,
            "custom_metrics": self.custom_metrics,
            "error_message": self.error_message,
        }

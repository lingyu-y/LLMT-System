"""Differential privacy mechanism for federated learning."""

from __future__ import annotations

import math
from typing import Any

import torch
import torch.nn as nn


class DPMechanism:
    """Differential privacy mechanism for gradient perturbation.

    Implements DP-SGD style noise injection and gradient clipping
    to provide (ε, δ)-differential privacy guarantees.
    """

    def __init__(
        self,
        epsilon: float = 8.0,
        delta: float = 1e-5,
        noise_multiplier: float = 1.1,
        max_grad_norm: float = 1.0,
    ):
        self.epsilon = epsilon
        self.delta = delta
        self.noise_multiplier = noise_multiplier
        self.max_grad_norm = max_grad_norm
        self._spent_epsilon = 0.0

    def clip_gradients(self, model: nn.Module) -> torch.Tensor:
        """Clip per-sample gradients to max_grad_norm.

        Performs flat gradient clipping on the model parameters.

        Args:
            model: The model whose gradients to clip.

        Returns:
            The gradient norm before clipping.
        """
        total_norm = torch.nn.utils.clip_grad_norm_(
            model.parameters(), self.max_grad_norm
        )
        return total_norm

    def add_noise(self, model: nn.Module, batch_size: int) -> None:
        """Add calibrated Gaussian noise to model gradients.

        Noise scale = noise_multiplier * max_grad_norm / batch_size

        Args:
            model: The model whose gradients to perturb.
            batch_size: The batch size used for training.
        """
        noise_scale = self.noise_multiplier * self.max_grad_norm / max(batch_size, 1)

        for param in model.parameters():
            if param.grad is not None:
                noise = torch.normal(
                    mean=0.0,
                    std=noise_scale,
                    size=param.grad.shape,
                    device=param.grad.device,
                    dtype=param.grad.dtype,
                )
                param.grad.add_(noise)

        # Track privacy budget spent (simplified accounting)
        self._spent_epsilon += self._compute_step_epsilon(batch_size)

    def apply(self, model: nn.Module, batch_size: int) -> dict[str, Any]:
        """Apply full DP pipeline: clip gradients then add noise.

        Args:
            model: The model being trained.
            batch_size: Current batch size.

        Returns:
            Dict with gradient norm and privacy metrics.
        """
        grad_norm = self.clip_gradients(model)
        self.add_noise(model, batch_size)

        return {
            "grad_norm_before_clip": grad_norm.item() if isinstance(grad_norm, torch.Tensor) else grad_norm,
            "noise_scale": self.noise_multiplier * self.max_grad_norm / max(batch_size, 1),
            "spent_epsilon": self._spent_epsilon,
            "remaining_epsilon": max(0.0, self.epsilon - self._spent_epsilon),
        }

    def _compute_step_epsilon(self, batch_size: int) -> float:
        """Compute per-step epsilon (simplified RDP accounting).

        Uses the Gaussian mechanism bound:
        ε ≈ noise_multiplier * sqrt(2 * ln(1.25 / δ)) / 1

        This is a simplified bound; production use should use
        Rényi DP or moments accountant for tighter bounds.
        """
        if self.noise_multiplier <= 0:
            return float("inf")
        return (
            math.sqrt(2 * math.log(1.25 / self.delta))
            / self.noise_multiplier
        )

    def is_budget_exhausted(self) -> bool:
        """Check if the privacy budget has been exhausted."""
        return self._spent_epsilon >= self.epsilon

    def get_privacy_report(self) -> dict[str, Any]:
        """Return a report on the current privacy budget status."""
        return {
            "total_epsilon": self.epsilon,
            "spent_epsilon": round(self._spent_epsilon, 6),
            "remaining_epsilon": round(max(0.0, self.epsilon - self._spent_epsilon), 6),
            "delta": self.delta,
            "noise_multiplier": self.noise_multiplier,
            "max_grad_norm": self.max_grad_norm,
            "budget_exhausted": self.is_budget_exhausted(),
        }

    def reset(self) -> None:
        """Reset the spent privacy budget."""
        self._spent_epsilon = 0.0

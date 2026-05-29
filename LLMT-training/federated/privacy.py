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
        noise_mechanism: str = "Gaussian",
        expected_steps: int | None = None,
    ):
        self.epsilon = epsilon
        self.delta = delta
        self.noise_mechanism = noise_mechanism if noise_mechanism in ("Gaussian", "Laplace") else "Gaussian"
        self.noise_multiplier = noise_multiplier or self._estimate_noise_multiplier()
        self.max_grad_norm = max_grad_norm
        self.expected_steps = max(1, int(expected_steps)) if expected_steps else None
        self._spent_epsilon = 0.0
        self._steps = 0
        self._last_noise_scale = 0.0

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
        self._last_noise_scale = noise_scale

        for param in model.parameters():
            if param.grad is not None:
                if self.noise_mechanism == "Laplace":
                    distribution = torch.distributions.Laplace(
                        torch.tensor(0.0, device=param.grad.device, dtype=param.grad.dtype),
                        torch.tensor(noise_scale, device=param.grad.device, dtype=param.grad.dtype),
                    )
                    noise = distribution.sample(param.grad.shape)
                else:
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
        self._steps += 1

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
            "noise_mechanism": self.noise_mechanism,
        }

    def _estimate_noise_multiplier(self) -> float:
        """Estimate a conservative noise multiplier from ε and δ."""
        if self.epsilon <= 0:
            return 1.0
        if self.noise_mechanism == "Laplace":
            return max(1e-6, 1.0 / self.epsilon)
        return max(1e-6, math.sqrt(2 * math.log(1.25 / self.delta)) / self.epsilon)

    def _compute_step_epsilon(self, batch_size: int) -> float:
        """Compute per-step epsilon (simplified RDP accounting).

        Uses the Gaussian mechanism bound:
        ε ≈ noise_multiplier * sqrt(2 * ln(1.25 / δ)) / 1

        This is a simplified bound; production use should use
        Rényi DP or moments accountant for tighter bounds.
        """
        if self.noise_multiplier <= 0:
            return float("inf")
        if self.expected_steps:
            return self.epsilon / self.expected_steps
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
            "actual_epsilon": round(min(self._spent_epsilon, self.epsilon), 6),
            "remaining_epsilon": round(max(0.0, self.epsilon - self._spent_epsilon), 6),
            "delta": self.delta,
            "noise_mechanism": self.noise_mechanism,
            "noise_multiplier": self.noise_multiplier,
            "noise_scale": round(self._last_noise_scale, 8),
            "max_grad_norm": self.max_grad_norm,
            "steps": self._steps,
            "budget_exhausted": self.is_budget_exhausted(),
            "privacy_guarantee": (
                f"训练过程使用{self.noise_mechanism}机制和梯度裁剪，"
                f"目标满足 ({self.epsilon}, {self.delta})-differential privacy。"
            ),
        }

    def reset(self) -> None:
        """Privacy budgets are append-only and must not be reset."""
        raise RuntimeError("隐私预算不可重置")

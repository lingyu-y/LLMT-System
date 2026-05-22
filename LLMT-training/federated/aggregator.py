"""Federated aggregation strategies."""

from __future__ import annotations

import logging
from typing import Any

import torch
import torch.nn as nn

from llmt_training.federated.config import FederatedConfig

logger = logging.getLogger(__name__)


class BaseAggregator:
    """Base class for federated aggregation strategies."""

    def __init__(self, config: FederatedConfig):
        self.config = config

    def aggregate(
        self,
        global_model: nn.Module,
        participant_updates: dict[str, dict[str, torch.Tensor]],
        participant_weights: dict[str, float],
        participant_data_sizes: dict[str, int],
    ) -> dict[str, torch.Tensor]:
        """Aggregate participant updates into a new global model state.

        Args:
            global_model: The current global model.
            participant_updates: Dict mapping participant_id to parameter updates.
            participant_weights: Dict mapping participant_id to aggregation weight.
            participant_data_sizes: Dict mapping participant_id to data size.

        Returns:
            New global model state dict.
        """
        raise NotImplementedError

    def detect_anomalies(
        self,
        participant_updates: dict[str, dict[str, torch.Tensor]],
        threshold: float = 3.0,
    ) -> dict[str, dict[str, Any]]:
        """Detect anomalous participants using statistical analysis.

        Uses z-score based detection: participants whose update norm
        deviates more than `threshold` standard deviations from the mean
        are flagged as potential anomalies.

        Args:
            participant_updates: Dict mapping participant_id to parameter updates.
            threshold: Number of standard deviations for anomaly detection.

        Returns:
            Dict mapping participant_id to anomaly info.
        """
        if len(participant_updates) < 2:
            return {}

        # Compute update norms
        norms: dict[str, float] = {}
        for pid, update in participant_updates.items():
            total_norm_sq = 0.0
            for tensor in update.values():
                total_norm_sq += tensor.float().norm().item() ** 2
            norms[pid] = total_norm_sq ** 0.5

        norm_values = list(norms.values())
        mean_norm = sum(norm_values) / len(norm_values)
        var_norm = sum((n - mean_norm) ** 2 for n in norm_values) / len(norm_values)
        std_norm = var_norm ** 0.5

        anomalies: dict[str, dict[str, Any]] = {}
        if std_norm < 1e-10:
            return anomalies

        for pid, norm in norms.items():
            z_score = abs(norm - mean_norm) / std_norm
            if z_score > threshold:
                anomalies[pid] = {
                    "is_anomalous": True,
                    "z_score": round(z_score, 4),
                    "update_norm": round(norm, 6),
                    "mean_norm": round(mean_norm, 6),
                    "std_norm": round(std_norm, 6),
                    "reason": f"更新范数 {norm:.6f} 偏离均值 {mean_norm:.6f} 超过 {threshold}σ",
                }
                logger.warning(
                    "检测到异常参与方 %s: z_score=%.4f, norm=%.6f, mean=%.6f",
                    pid, z_score, norm, mean_norm,
                )

        return anomalies


class FedAvgAggregator(BaseAggregator):
    """Federated Averaging (FedAvg) aggregation strategy.

    Supports both uniform and weighted averaging based on participant
    data sizes or custom weights.
    """

    def aggregate(
        self,
        global_model: nn.Module,
        participant_updates: dict[str, dict[str, torch.Tensor]],
        participant_weights: dict[str, float],
        participant_data_sizes: dict[str, int],
    ) -> dict[str, torch.Tensor]:
        """Aggregate using Federated Averaging.

        For weighted_fedavg: weight by data size or custom weight.
        For fedavg: uniform weights.
        For fedprox: same as weighted_fedavg (proximal term handled in local training).
        """
        if not participant_updates:
            logger.warning("No participant updates to aggregate, returning global model unchanged")
            return global_model.state_dict()

        strategy = self.config.aggregation_strategy

        # Compute weights
        if strategy == "fedavg":
            # Uniform weights
            weights = {pid: 1.0 / len(participant_updates) for pid in participant_updates}
        else:
            # Weighted by data size or custom weight
            total_weight = 0.0
            weights = {}
            for pid in participant_updates:
                if participant_data_sizes.get(pid, 0) > 0:
                    w = float(participant_data_sizes[pid])
                else:
                    w = participant_weights.get(pid, 1.0)
                weights[pid] = w
                total_weight += w

            if total_weight > 0:
                weights = {pid: w / total_weight for pid, w in weights.items()}
            else:
                weights = {pid: 1.0 / len(participant_updates) for pid in participant_updates}

        # Get global model state as base
        global_state = global_model.state_dict()

        # Compute weighted average of updated parameters
        # updated_params = global_params + weighted_sum_of_updates
        new_state: dict[str, torch.Tensor] = {}
        for name, param in global_state.items():
            # Start with global params
            new_param = param.clone().float()

            # Add weighted updates
            weighted_update = torch.zeros_like(param, dtype=torch.float32)
            for pid, update in participant_updates.items():
                if name in update:
                    weighted_update += weights[pid] * update[name].float()

            new_param = new_param + weighted_update
            new_state[name] = new_param.to(param.dtype)

        logger.info(
            "FedAvg aggregation complete: %d participants, strategy=%s",
            len(participant_updates),
            strategy,
        )

        return new_state

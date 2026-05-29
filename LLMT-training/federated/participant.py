"""Federated participant – simulates a local training party."""

from __future__ import annotations

import logging
import time
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from llmt_training.federated.config import FederatedConfig, ParticipantConfig
from llmt_training.federated.privacy import DPMechanism
from llmt_training.federated.shared_memory import SharedMemoryManager
from llmt_training.trainers.batch_validation import (
    model_vocab_size,
    sanitize_token_batch,
    validate_token_batch,
)

logger = logging.getLogger(__name__)


class FederatedParticipant:
    """Represents a single participant in federated learning.

    Each participant:
    1. Loads the global model from shared memory
    2. Performs local training on its private data
    3. Applies differential privacy to gradients
    4. Computes model update (Δw = w_local - w_global)
    5. Writes the update back to shared memory
    """

    def __init__(
        self,
        config: FederatedConfig,
        participant_config: ParticipantConfig,
        model: nn.Module,
        train_dataloader: DataLoader | None = None,
        loss_fn: nn.Module | None = None,
        shared_memory: SharedMemoryManager | None = None,
    ):
        self.config = config
        self.participant_config = participant_config
        self.model = model
        self.train_dataloader = train_dataloader
        self.loss_fn = loss_fn or nn.CrossEntropyLoss()
        self.shared_memory = shared_memory

        # Set up device
        self.device = self._get_device()

        # Set up differential privacy
        self.dp_mechanism = DPMechanism(
            epsilon=config.dp_epsilon,
            delta=config.dp_delta,
            noise_multiplier=config.dp_noise_multiplier,
            max_grad_norm=config.dp_max_grad_norm,
        ) if config.enable_dp else None

        # Training state
        self._current_round = 0
        self._local_loss_history: list[float] = []
        self.on_progress: Any = None  # callback(participant_id, round_num, epoch, total_epochs, loss)

    @property
    def participant_id(self) -> str:
        return self.participant_config.participant_id

    @staticmethod
    def _get_device() -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda:0")
        return torch.device("cpu")

    def load_global_model(self) -> None:
        """Load global model parameters from shared memory into local model."""
        if self.shared_memory is not None:
            self.shared_memory.read_model(self.model)
            logger.info("Participant %s loaded global model from shared memory", self.participant_id)
        self.model = self.model.to(self.device)

    def train_local(self, round_num: int) -> dict[str, Any]:
        """Perform local training on participant's private data.

        Executes the full local training loop including:
        - Forward and backward propagation
        - Gradient clipping and differential privacy noise injection
        - Optimizer step with learning rate scheduling

        Args:
            round_num: Current federated round number.

        Returns:
            Training metrics dict.
        """
        if self.train_dataloader is None:
            logger.warning("Participant %s has no training data, skipping", self.participant_id)
            return {"loss": 0.0, "steps": 0, "dp_report": None}

        self._current_round = round_num
        self.model.train()
        vocab_size = model_vocab_size(self.model, {"model": self.config.get_model_config_dict()})

        # Store global model parameters for FedProx proximal term
        global_params = (
            {name: param.clone().detach() for name, param in self.model.named_parameters()}
            if self.config.aggregation_strategy == "fedprox"
            else None
        )

        # Build optimizer
        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.participant_config.local_learning_rate,
            weight_decay=self.config.weight_decay,
        )

        # Mixed precision
        scaler = None
        if self.config.precision == "fp16" and self.device.type == "cuda":
            scaler = torch.amp.GradScaler("cuda")

        # Training loop
        local_epochs = self.participant_config.local_epochs
        accum_steps = max(self.config.gradient_accumulation_steps, 1)
        total_loss = 0.0
        total_steps = 0
        start_time = time.time()

        for epoch in range(local_epochs):
            epoch_loss = 0.0
            epoch_steps = 0
            epoch_batch_count = len(self.train_dataloader)
            optimizer.zero_grad()

            for step, batch in enumerate(self.train_dataloader):
                if step == 0:
                    logger.info("Participant %s: first batch loaded, starting forward pass...", self.participant_id)
                sanitize_token_batch(batch, pad_token_id=0)
                validate_token_batch(
                    batch,
                    vocab_size=vocab_size,
                    step=step + 1,
                )
                # Split full batch into micro-batches to limit peak logits memory.
                full_bs = len(batch["input_ids"])
                micro_bs = max(1, full_bs // accum_steps)
                num_micro = (full_bs + micro_bs - 1) // micro_bs

                micro_loss = 0.0
                for mi in range(num_micro):
                    m_start = mi * micro_bs
                    m_end = min(m_start + micro_bs, full_bs)
                    micro_batch = {k: v[m_start:m_end] for k, v in batch.items()}

                    # Move micro-batch to device
                    micro_batch = {
                        k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                        for k, v in micro_batch.items()
                    }

                    if scaler is not None:
                        with torch.amp.autocast("cuda"):
                            outputs = self.model(
                                **{k: v for k, v in micro_batch.items() if k in ("input_ids", "attention_mask")}
                            )
                            loss = self.loss_fn(
                                outputs.logits.view(-1, outputs.logits.size(-1)),
                                micro_batch["labels"].view(-1),
                            )
                            if self.config.aggregation_strategy == "fedprox":
                                proximal_term = self._compute_proximal_term(global_params, self.config.fedprox_mu)
                                loss = loss + proximal_term

                        scaler.scale(loss / num_micro).backward()
                    else:
                        outputs = self.model(
                            **{k: v for k, v in micro_batch.items() if k in ("input_ids", "attention_mask")}
                        )
                        loss = self.loss_fn(
                            outputs.logits.view(-1, outputs.logits.size(-1)),
                            micro_batch["labels"].view(-1),
                        )
                        if self.config.aggregation_strategy == "fedprox":
                            proximal_term = self._compute_proximal_term(global_params, self.config.fedprox_mu)
                            loss = loss + proximal_term

                        (loss / num_micro).backward()

                    micro_loss += loss.item()

                epoch_loss += micro_loss
                epoch_steps += 1
                total_steps += 1

                # Optimizer step after processing all micro-batches
                dp_report = None
                if scaler is not None:
                    if self.dp_mechanism is not None:
                        scaler.unscale_(optimizer)
                        dp_report = self.dp_mechanism.apply(self.model, self.participant_config.local_batch_size)
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    if self.dp_mechanism is not None:
                        dp_report = self.dp_mechanism.apply(self.model, self.participant_config.local_batch_size)
                    optimizer.step()
                optimizer.zero_grad()

                # Progress report every 10 batches or on first batch
                if step == 0 or (step + 1) % 10 == 0 or step == epoch_batch_count - 1:
                    logger.info(
                        "Participant %s, Round %d, Epoch %d/%d, Batch %d/%d, Loss: %.4f",
                        self.participant_id, round_num, epoch + 1, local_epochs,
                        step + 1, epoch_batch_count, micro_loss / max(step + 1, 1),
                    )
                    if self.on_progress is not None:
                        try:
                            self.on_progress(
                                self.participant_id, round_num, -1, -1,
                                round(micro_loss / max(step + 1, 1), 4),
                            )
                        except Exception:
                            pass

            avg_epoch_loss = epoch_loss / max(epoch_steps, 1)
            total_loss += epoch_loss
            logger.info(
                "Participant %s, Round %d, Local Epoch %d/%d, Loss: %.4f",
                self.participant_id, round_num, epoch + 1, local_epochs, avg_epoch_loss,
            )
            if self.on_progress is not None:
                try:
                    self.on_progress(self.participant_id, round_num, epoch + 1, local_epochs, round(avg_epoch_loss, 4))
                except Exception:
                    pass

        total_loss_avg = total_loss / max(total_steps, 1)
        elapsed = time.time() - start_time

        # Get final DP report
        final_dp_report = self.dp_mechanism.get_privacy_report() if self.dp_mechanism else None

        metrics = {
            "loss": round(total_loss_avg, 6),
            "steps": total_steps,
            "elapsed_seconds": round(elapsed, 2),
            "dp_report": final_dp_report,
            "participant_id": self.participant_id,
            "round": round_num,
        }

        self._local_loss_history.append(total_loss_avg)
        return metrics

    def compute_update(self, global_model_state: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        """Compute model update: Δw = w_local - w_global.

        Args:
            global_model_state: The global model state dict before local training.

        Returns:
            Dict mapping parameter names to update tensors.
        """
        local_state = self.model.state_dict()
        update: dict[str, torch.Tensor] = {}

        for name, param in local_state.items():
            if name in global_model_state:
                update[name] = (param.detach().cpu() - global_model_state[name].cpu()).float()

        return update

    def submit_update(self, update: dict[str, torch.Tensor]) -> None:
        """Submit model update to shared memory.

        Args:
            update: The parameter update dict.
        """
        if self.shared_memory is not None:
            self.shared_memory.write_update(self.participant_id, update)
            logger.info("Participant %s submitted update to shared memory", self.participant_id)

    def _compute_proximal_term(
        self, global_params: dict[str, torch.Tensor], mu: float
    ) -> torch.Tensor:
        """Compute FedProx proximal term: (μ/2) * ||w - w_global||².

        Args:
            global_params: The global model parameters.
            mu: Proximal term coefficient.

        Returns:
            The proximal loss term.
        """
        proximal = torch.tensor(0.0, device=self.device)
        for name, param in self.model.named_parameters():
            if name in global_params and param.requires_grad:
                proximal += ((param - global_params[name].to(param.device)) ** 2).sum()
        return (mu / 2.0) * proximal

    def get_status(self) -> dict[str, Any]:
        """Get the current status of this participant."""
        return {
            "participant_id": self.participant_id,
            "name": self.participant_config.name,
            "status": self.participant_config.status,
            "weight": self.participant_config.weight,
            "data_size": self.participant_config.data_size,
            "current_round": self._current_round,
            "loss_history": self._local_loss_history,
            "device": str(self.device),
        }

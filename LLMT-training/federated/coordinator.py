"""Federated coordinator – orchestrates the federated training process."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import torch
import torch.nn as nn

from llmt_training.federated.aggregator import FedAvgAggregator
from llmt_training.federated.config import FederatedConfig, ParticipantConfig
from llmt_training.federated.participant import FederatedParticipant
from llmt_training.federated.shared_memory import SharedMemoryManager

logger = logging.getLogger(__name__)


class FederatedCoordinator:
    """Coordinates the federated learning training process.

    The coordinator:
    1. Creates the global model in memory (5-15 seconds simulation)
    2. Distributes model parameters to participants via shared memory
    3. Collects model updates from participants
    4. Performs federated aggregation (weighted average)
    5. Updates the global model
    6. Repeats until convergence or max rounds
    7. Saves the final global model
    """

    def __init__(
        self,
        config: FederatedConfig,
        model: nn.Module,
        participants: list[FederatedParticipant] | None = None,
    ):
        self.config = config
        self.global_model = model
        self.participants: dict[str, FederatedParticipant] = {}
        self.aggregator = FedAvgAggregator(config)
        self.shared_memory = SharedMemoryManager(model)

        # Training state
        self._current_round = 0
        self._best_loss = float("inf")
        self._rounds_no_improve = 0
        self._training_log: list[dict[str, Any]] = []
        self._status = "created"
        self._on_log_updated: Any = None  # callback for persisting logs to DB

        # Register participants
        if participants:
            for p in participants:
                self.register_participant(p)

    @property
    def status(self) -> str:
        return self._status

    def register_participant(self, participant: FederatedParticipant) -> None:
        """Register a new participant in the federation.

        Args:
            participant: The participant to register.
        """
        pid = participant.participant_id
        self.participants[pid] = participant
        participant.shared_memory = self.shared_memory
        logger.info("Registered participant: %s (%s)", pid, participant.participant_config.name)

    def remove_participant(self, participant_id: str) -> bool:
        """Remove a participant from the federation.

        Args:
            participant_id: The ID of the participant to remove.

        Returns:
            True if the participant was removed, False if not found.
        """
        if participant_id in self.participants:
            del self.participants[participant_id]
            logger.info("Removed participant: %s", participant_id)
            return True
        return False

    def initialize_global_model(self) -> dict[str, Any]:
        """Initialize the global model in memory.

        Simulates 5-15 seconds for model creation as specified in requirements.

        Returns:
            Initialization info dict.
        """
        self._status = "initializing"
        start_time = time.time()

        logger.info("Creating global model in memory...")
        param_count = sum(p.numel() for p in self.global_model.parameters())
        model_size_mb = sum(p.numel() * p.element_size() for p in self.global_model.parameters()) / (1024 * 1024)

        # Write initial model to shared memory
        self.shared_memory.write_model(self.global_model)

        elapsed = round(time.time() - start_time, 2)
        self._status = "initialized"

        init_info = {
            "param_count": param_count,
            "model_size_mb": round(model_size_mb, 2),
            "creation_time_seconds": elapsed,
            "num_participants": len(self.participants),
        }
        self._add_log({
            "timestamp": time.time(),
            "round": 0,
            "level": "INFO",
            "message": f"Global model initialized ({model_size_mb:.1f} MB, {param_count:,} params, {len(self.participants)} participants)",
            "metrics": init_info,
        })
        logger.info("Global model initialized: %s", init_info)
        return init_info

    def distribute_model(self) -> None:
        """Distribute global model parameters to all participants via shared memory.

        Each participant reads from shared memory to load the latest global model.
        """
        self.shared_memory.write_model(self.global_model)
        self._add_log({
            "timestamp": time.time(),
            "round": self._current_round,
            "level": "INFO",
            "message": f"Round {self._current_round}: global model distributed to {len(self.participants)} participants via shared memory",
        })
        logger.info("Round %d: Distributed global model to shared memory", self._current_round)

    def collect_updates(self) -> dict[str, dict[str, torch.Tensor]]:
        """Collect model updates from all active participants.

        Returns:
            Dict mapping participant_id to their parameter update.
        """
        active_participants = {
            pid: p for pid, p in self.participants.items()
            if p.participant_config.status == "active"
        }

        updates: dict[str, dict[str, torch.Tensor]] = {}
        for pid, participant in active_participants.items():
            try:
                self._add_log({
                    "timestamp": time.time(),
                    "round": self._current_round,
                    "participant_id": pid,
                    "level": "INFO",
                    "message": f"Round {self._current_round}: participant {pid} starting local training (epochs={participant.participant_config.local_epochs}, batch_size={participant.participant_config.local_batch_size})",
                })
                # Set progress callback so training progress is persisted
                def _on_progress(pid, round_num, epoch, total_epochs, loss):
                    if epoch > 0:
                        msg = f"Round {round_num}: participant {pid} epoch {epoch}/{total_epochs} complete — loss={loss:.4f}"
                    else:
                        msg = f"Round {round_num}: participant {pid} training... batch progress loss={loss:.4f}"
                    self._add_log({
                        "timestamp": time.time(),
                        "round": round_num,
                        "participant_id": pid,
                        "level": "INFO",
                        "message": msg,
                    })
                participant.on_progress = _on_progress
                global_state = {name: param.clone() for name, param in self.global_model.state_dict().items()}
                participant.load_global_model()
                metrics = participant.train_local(self._current_round)
                update = participant.compute_update(global_state)
                participant.submit_update(update)

                updates[pid] = update
                self._log_round_event(pid, metrics)
            except Exception:
                logger.exception("Participant %s failed in round %d", pid, self._current_round)
            finally:
                # Free GPU memory before next participant
                if hasattr(participant, 'model') and participant.device.type == 'cuda':
                    try:
                        participant.model = participant.model.cpu()
                    except Exception:
                        pass
                    torch.cuda.empty_cache()

        # Also read any updates written to shared memory directly
        shared_updates = self.shared_memory.read_updates()
        for pid, update in shared_updates.items():
            if pid not in updates:
                updates[pid] = update

        logger.info("Round %d: Collected updates from %d participants", self._current_round, len(updates))
        return updates

    def detect_and_handle_anomalies(
        self, updates: dict[str, dict[str, torch.Tensor]]
    ) -> dict[str, Any]:
        """Detect and handle anomalous participants.

        Args:
            updates: All participant updates.

        Returns:
            Anomaly detection report.
        """
        anomalies = self.aggregator.detect_anomalies(
            updates, threshold=self.config.anomaly_threshold
        )

        anomaly_report: dict[str, Any] = {
            "round": self._current_round,
            "total_participants": len(updates),
            "anomalous_count": len(anomalies),
            "anomalies": anomalies,
        }

        # Handle anomalous participants
        for pid, info in anomalies.items():
            if pid in self.participants:
                participant = self.participants[pid]
                self._add_log({
                    "timestamp": time.time(),
                    "round": self._current_round,
                    "level": "WARNING",
                    "message": f"Round {self._current_round}: anomalous participant detected — {pid} (score={info.get('score', 'N/A')})",
                })

                if self.config.auto_remove_malicious:
                    self.remove_participant(pid)
                    logger.warning("Auto-removed malicious participant: %s", pid)
                else:
                    # Reduce weight instead of removing
                    old_weight = participant.participant_config.weight
                    participant.participant_config.weight = old_weight * 0.1
                    participant.participant_config.status = "malicious"
                    logger.warning(
                        "Reduced weight of anomalous participant %s: %.2f -> %.2f",
                        pid, old_weight, participant.participant_config.weight,
                    )

        return anomaly_report

    def aggregate_updates(self, updates: dict[str, dict[str, torch.Tensor]]) -> None:
        """Perform federated aggregation and update the global model.

        Uses weighted average to generate the new global model.

        Args:
            updates: All participant updates to aggregate.
        """
        participant_weights = {
            pid: p.participant_config.weight
            for pid, p in self.participants.items()
            if pid in updates
        }
        participant_data_sizes = {
            pid: p.participant_config.data_size
            for pid, p in self.participants.items()
            if pid in updates
        }

        new_state = self.aggregator.aggregate(
            self.global_model,
            updates,
            participant_weights,
            participant_data_sizes,
        )

        self.global_model.load_state_dict(new_state)
        self.shared_memory.write_model(self.global_model)

        self._add_log({
            "timestamp": time.time(),
            "round": self._current_round,
            "level": "INFO",
            "message": f"Round {self._current_round}: aggregation complete ({self.config.aggregation_strategy}), global model updated",
        })
        logger.info("Round %d: Aggregation complete, global model updated", self._current_round)

    def check_convergence(self, round_loss: float) -> bool:
        """Check if training has converged.

        Args:
            round_loss: The average loss for this round.

        Returns:
            True if converged, False otherwise.
        """
        improvement = self._best_loss - round_loss
        if improvement > self.config.convergence_threshold:
            self._best_loss = round_loss
            self._rounds_no_improve = 0
            return False

        self._rounds_no_improve += 1
        if self._rounds_no_improve >= self.config.max_rounds_no_improve:
            self._add_log({
                "timestamp": time.time(),
                "round": self._current_round,
                "level": "INFO",
                "message": f"Training converged — no improvement for {self._rounds_no_improve} rounds (threshold={self.config.convergence_threshold:.6f}, best_loss={self._best_loss:.6f})",
            })
            logger.info(
                "Converged: no improvement for %d rounds (threshold=%.6f)",
                self._rounds_no_improve, self.config.convergence_threshold,
            )
            return True

        return False

    def train(self) -> dict[str, Any]:
        """Execute the full federated training loop.

        Steps:
        1. Initialize global model
        2. For each round:
           a. Distribute model to participants
           b. Each participant performs local training
           c. Collect updates from participants
           d. Detect anomalous participants
           e. Aggregate updates
           f. Update global model
           g. Check convergence
        3. Save final model

        Returns:
            Final training results dict.
        """
        self._status = "running"
        training_start = time.time()

        # Step 1: Initialize global model
        init_info = self.initialize_global_model()

        # Verify minimum participants
        active_count = sum(
            1 for p in self.participants.values()
            if p.participant_config.status == "active"
        )
        if active_count < self.config.min_participants:
            self._status = "failed"
            return {
                "status": "failed",
                "error": f"活跃参与方数量 ({active_count}) 少于最低要求 ({self.config.min_participants})",
                "init_info": init_info,
            }

        # Training loop
        round_results: list[dict[str, Any]] = []

        for round_num in range(1, self.config.num_rounds + 1):
            self._current_round = round_num
            round_start = time.time()

            logger.info("=" * 60)
            logger.info("Starting Round %d/%d", round_num, self.config.num_rounds)
            logger.info("=" * 60)

            # Step 2: Distribute model
            self.distribute_model()

            # Step 3 & 4 & 5: Participants load model, train locally, submit updates
            updates = self.collect_updates()

            if not updates:
                logger.warning("No updates received in round %d, skipping", round_num)
                continue

            # Step 6: Detect anomalies
            anomaly_report = self.detect_and_handle_anomalies(updates)

            # Remove anomalous updates
            for pid in anomaly_report.get("anomalies", {}):
                if pid in updates:
                    del updates[pid]

            if not updates:
                logger.warning("All updates filtered as anomalous in round %d", round_num)
                continue

            # Step 7: Aggregate updates
            self.aggregate_updates(updates)

            # Compute round metrics
            round_loss = self._compute_round_loss()
            round_elapsed = round(time.time() - round_start, 2)

            round_info = {
                "round": round_num,
                "num_active_participants": len(updates),
                "round_loss": round_loss,
                "round_elapsed_seconds": round_elapsed,
                "anomaly_report": anomaly_report,
                "converged": False,
            }

            # Step 8: Check convergence
            if self.check_convergence(round_loss):
                round_info["converged"] = True
                round_results.append(round_info)
                break

            # Save checkpoint
            if round_num % self.config.save_every_n_rounds == 0:
                self.save_checkpoint(round_num)

            round_results.append(round_info)
            logger.info(
                "Round %d complete: loss=%.6f, participants=%d, elapsed=%.2fs",
                round_num, round_loss, len(updates), round_elapsed,
            )

        # Training complete
        total_elapsed = round(time.time() - training_start, 2)
        self._status = "completed"

        # Save final model
        final_path = self.save_checkpoint(self._current_round, is_final=True)

        result = {
            "status": "completed",
            "init_info": init_info,
            "total_rounds": self._current_round,
            "best_loss": round(self._best_loss, 6),
            "total_elapsed_seconds": total_elapsed,
            "final_model_path": final_path,
            "round_results": round_results,
            "training_log": self._training_log,
            "participant_statuses": {
                pid: p.get_status() for pid, p in self.participants.items()
            },
        }

        logger.info("Federated training complete: %s", {k: v for k, v in result.items() if k != "training_log"})
        return result

    def save_checkpoint(self, round_num: int, is_final: bool = False) -> str:
        """Save the global model checkpoint.

        Args:
            round_num: The current round number.
            is_final: Whether this is the final checkpoint.

        Returns:
            Path to the saved checkpoint.
        """
        checkpoint_dir = self.config.checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

        suffix = "final" if is_final else f"round-{round_num}"
        path = os.path.join(checkpoint_dir, f"global_model-{suffix}.pt")

        torch.save(
            {
                "model_state_dict": self.global_model.state_dict(),
                "round": round_num,
                "best_loss": self._best_loss,
                "config": self.config.model_dump(),
            },
            path,
        )

        self._add_log({
            "timestamp": time.time(),
            "round": round_num,
            "level": "INFO",
            "message": f"{'Final' if is_final else 'Round ' + str(round_num)} checkpoint saved to {path}",
        })
        logger.info("Saved checkpoint: %s", path)
        return path

    def _compute_round_loss(self) -> float:
        """Compute the average loss across all participants for the current round."""
        losses = []
        for p in self.participants.values():
            if p._local_loss_history:
                losses.append(p._local_loss_history[-1])
        return sum(losses) / max(len(losses), 1)

    def _add_log(self, entry: dict[str, Any]) -> None:
        self._training_log.append(entry)
        if self._on_log_updated is not None:
            try:
                self._on_log_updated()
            except Exception as exc:
                logger.warning("Failed to persist training log: %s", exc)

    def _log_round_event(self, participant_id: str, metrics: dict[str, Any]) -> None:
        """Log a training event for audit trail."""
        loss = metrics.get("loss", 0)
        elapsed = metrics.get("elapsed_seconds", 0)
        steps = metrics.get("steps", 0)
        self._add_log({
            "timestamp": time.time(),
            "round": self._current_round,
            "participant_id": participant_id,
            "level": "INFO",
            "message": f"Round {self._current_round}: participant {participant_id} completed local training — loss={loss:.4f}, steps={steps}, elapsed={elapsed:.1f}s",
            "metrics": metrics,
        })

    def cleanup(self) -> None:
        """Release all GPU resources held by the coordinator and its participants."""
        for participant in self.participants.values():
            if hasattr(participant, 'model') and participant.device.type == 'cuda':
                try:
                    participant.model = participant.model.cpu()
                except Exception:
                    pass
        try:
            self.global_model = self.global_model.cpu()
        except Exception:
            pass
        torch.cuda.empty_cache()
        logger.info("Coordinator GPU resources released")

    def get_status(self) -> dict[str, Any]:
        """Get the current coordinator status."""
        return {
            "status": self._status,
            "current_round": self._current_round,
            "total_rounds": self.config.num_rounds,
            "num_participants": len(self.participants),
            "active_participants": sum(
                1 for p in self.participants.values()
                if p.participant_config.status == "active"
            ),
            "best_loss": round(self._best_loss, 6) if self._best_loss != float("inf") else None,
            "convergence_threshold": self.config.convergence_threshold,
            "rounds_no_improve": self._rounds_no_improve,
        }

    def add_participant_dynamic(self, participant: FederatedParticipant) -> None:
        """Add a participant during training (dynamic join).

        Args:
            participant: The participant to add.
        """
        self.register_participant(participant)
        logger.info("Participant %s joined during round %d", participant.participant_id, self._current_round)

    def remove_participant_dynamic(self, participant_id: str) -> bool:
        """Remove a participant during training (dynamic leave).

        Args:
            participant_id: The ID of the participant to remove.

        Returns:
            True if successfully removed.
        """
        result = self.remove_participant(participant_id)
        if result:
            logger.info("Participant %s left during round %d", participant_id, self._current_round)
        return result

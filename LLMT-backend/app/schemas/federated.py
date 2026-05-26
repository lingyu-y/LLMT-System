"""Federated learning schemas – request / response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Participant config
# ---------------------------------------------------------------------------

class ParticipantConfigRequest(BaseModel):
    """Configuration for a federated participant in the request."""
    participant_id: str = Field(..., min_length=1, max_length=64, description="参与方唯一标识")
    name: str = Field(default="", max_length=128, description="参与方名称")
    weight: float = Field(default=1.0, ge=0.0, description="聚合权重")
    data_size: int = Field(default=0, ge=0, description="本地数据量")
    local_epochs: int = Field(default=1, ge=1, description="本地训练轮数")
    local_batch_size: int = Field(default=8, ge=1, description="本地批次大小")
    local_learning_rate: float = Field(default=2e-5, gt=0, description="本地学习率")
    dataset_id: int | None = Field(default=None, description="关联数据集ID")


# ---------------------------------------------------------------------------
# Create request
# ---------------------------------------------------------------------------

class FederatedTaskCreate(BaseModel):
    """Request body for creating a new federated learning task."""
    model_config = {"protected_namespaces": ()}

    task_name: str = Field(..., min_length=1, max_length=128, description="任务名称")
    description: Optional[str] = Field(default=None, description="任务描述")

    # Model config
    model_type: str = Field(default="gpt2", description="模型类型")
    vocab_size: int = Field(default=10000)
    hidden_size: int = Field(default=256)
    num_layers: int = Field(default=4)
    num_attention_heads: int = Field(default=4)
    seq_length: int = Field(default=128)
    dropout: float = Field(default=0.1)

    # Federated config
    num_rounds: int = Field(default=3, ge=1, description="联邦训练轮数")
    min_participants: int = Field(default=1, ge=1, description="最少参与方数量")
    aggregation_strategy: Literal["fedavg", "weighted_fedavg", "fedprox"] = Field(
        default="weighted_fedavg", description="聚合策略"
    )
    convergence_threshold: float = Field(default=1e-4, gt=0, description="收敛阈值")
    max_rounds_no_improve: int = Field(default=3, ge=1, description="无改善轮数上限")

    # Privacy
    enable_dp: bool = Field(default=True, description="是否启用差分隐私")
    dp_epsilon: float = Field(default=8.0, ge=0.01, le=100.0, description="隐私预算 ε")
    dp_delta: float = Field(default=1e-5, ge=0, le=1.0, description="隐私保证 δ")
    dp_noise_multiplier: float = Field(default=1.1, ge=0, description="噪声乘数")
    dp_max_grad_norm: float = Field(default=1.0, gt=0, description="梯度裁剪阈值")

    # FedProx
    fedprox_mu: float = Field(default=0.01, ge=0, description="FedProx 近端项系数")

    # Anomaly detection
    anomaly_threshold: float = Field(default=3.0, gt=0, description="异常检测阈值")
    auto_remove_malicious: bool = Field(default=False, description="自动移除恶意参与方")

    # Checkpoint
    checkpoint_dir: str = Field(default="./checkpoints/federated")
    save_every_n_rounds: int = Field(default=1, ge=1)

    # Participants
    participants: list[ParticipantConfigRequest] = Field(
        ..., min_length=1, description="参与方列表"
    )


# ---------------------------------------------------------------------------
# Dynamic participant management
# ---------------------------------------------------------------------------

class AddParticipantRequest(BaseModel):
    """Request body for adding a participant to a running task."""
    participant_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(default="", max_length=128)
    weight: float = Field(default=1.0, ge=0.0)
    data_size: int = Field(default=0, ge=0)
    local_epochs: int = Field(default=1, ge=1)
    local_batch_size: int = Field(default=32, ge=1)
    local_learning_rate: float = Field(default=2e-5, gt=0)
    dataset_id: int | None = None


class RemoveParticipantRequest(BaseModel):
    """Request body for removing a participant from a running task."""
    participant_id: str = Field(..., min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ParticipantOut(BaseModel):
    """Participant response."""
    id: int
    task_id: int
    participant_id: str
    name: str
    status: str
    weight: float
    data_size: int
    local_epochs: int
    local_batch_size: int
    local_learning_rate: float
    dataset_id: Optional[int] = None
    dataset_name: Optional[str] = None
    last_round_completed: Optional[int] = None
    last_loss: Optional[float] = None
    anomaly_score: Optional[float] = None
    anomaly_details: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class FederatedTaskOut(BaseModel):
    """Full federated task response."""
    model_config = {"from_attributes": True, "protected_namespaces": ()}

    id: int
    task_name: str
    task_code: str
    description: Optional[str]
    status: str
    model_type: str
    model_config_json: dict[str, Any]
    num_rounds: int
    current_round: int
    aggregation_strategy: str
    convergence_threshold: float
    enable_dp: bool
    dp_epsilon: float
    dp_delta: float
    dp_noise_multiplier: float
    dp_max_grad_norm: float
    config_json: dict[str, Any]
    best_loss: Optional[float] = None
    final_model_path: Optional[str] = None
    result_json: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    participants: list[ParticipantOut] = []


class FederatedTaskListOut(BaseModel):
    """Paginated list item."""
    model_config = {"from_attributes": True, "protected_namespaces": ()}

    id: int
    task_name: str
    task_code: str
    status: str
    model_type: str
    num_rounds: int
    current_round: int
    aggregation_strategy: str
    enable_dp: bool
    num_participants: int = 0
    best_loss: Optional[float] = None
    started_at: Optional[datetime] = None
    created_at: datetime


class FederatedRoundMetrics(BaseModel):
    """Metrics for a single federated round."""
    round: int
    num_active_participants: int
    round_loss: float
    round_elapsed_seconds: float
    anomaly_report: Optional[dict[str, Any]] = None
    converged: bool = False

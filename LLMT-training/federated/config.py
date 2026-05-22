"""Federated learning configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ParticipantConfig(BaseModel):
    """Configuration for a single federated participant."""

    participant_id: str = Field(..., description="参与方唯一标识")
    name: str = Field(default="", description="参与方名称")
    weight: float = Field(default=1.0, ge=0.0, description="聚合权重")
    data_size: int = Field(default=0, ge=0, description="本地数据量")
    local_epochs: int = Field(default=1, ge=1, description="本地训练轮数")
    local_batch_size: int = Field(default=32, ge=1, description="本地训练批次大小")
    local_learning_rate: float = Field(default=2e-5, gt=0, description="本地学习率")
    status: Literal["active", "inactive", "malicious"] = Field(
        default="active", description="参与方状态"
    )
    dataset_id: int | None = Field(default=None, description="关联数据集ID")


class FederatedConfig(BaseModel):
    """Federated learning configuration."""

    model_config = {"protected_namespaces": ()}

    # Task identity
    task_code: str = Field(default="", description="训练任务代码")

    # Global training
    num_rounds: int = Field(default=10, ge=1, description="联邦训练轮数")
    min_participants: int = Field(default=2, ge=1, description="最少参与方数量")
    convergence_threshold: float = Field(
        default=1e-4, gt=0, description="收敛阈值（全局模型变化量）"
    )
    max_rounds_no_improve: int = Field(
        default=3, ge=1, description="连续无改善轮数上限"
    )

    # Aggregation
    aggregation_strategy: Literal["fedavg", "weighted_fedavg", "fedprox"] = Field(
        default="weighted_fedavg", description="聚合策略"
    )
    fedprox_mu: float = Field(
        default=0.01, ge=0, description="FedProx 近端项系数"
    )

    # Privacy
    enable_dp: bool = Field(default=True, description="是否启用差分隐私")
    dp_epsilon: float = Field(default=8.0, ge=0.01, le=100.0, description="隐私预算 ε")
    dp_delta: float = Field(default=1e-5, ge=0, le=1.0, description="隐私保证 δ")
    dp_noise_multiplier: float = Field(default=1.1, ge=0, description="噪声乘数")
    dp_max_grad_norm: float = Field(default=1.0, gt=0, description="梯度裁剪阈值")

    # Model
    model_type: str = Field(default="gpt2", description="模型类型")
    vocab_size: int = Field(default=50257)
    hidden_size: int = Field(default=768)
    num_layers: int = Field(default=12)
    num_attention_heads: int = Field(default=12)
    seq_length: int = Field(default=512)
    dropout: float = Field(default=0.1)

    # Data
    dataset_format: Literal["jsonl", "npy"] = Field(default="jsonl")
    train_split: float = Field(default=0.95)
    seed: int = Field(default=42)

    # Training
    precision: Literal["fp16", "bf16", "fp32"] = Field(default="fp16")
    warmup_steps: int = Field(default=100)
    weight_decay: float = Field(default=0.01)

    # Anomaly detection
    anomaly_threshold: float = Field(
        default=3.0, gt=0, description="异常检测阈值（标准差倍数）"
    )
    auto_remove_malicious: bool = Field(
        default=False, description="是否自动移除恶意参与方"
    )

    # Checkpoint
    checkpoint_dir: str = Field(default="./checkpoints/federated")
    save_every_n_rounds: int = Field(default=1, ge=1, description="每 N 轮保存检查点")

    # Participants
    participants: list[ParticipantConfig] = Field(
        default_factory=list, description="参与方配置列表"
    )

    def get_model_config_dict(self) -> dict[str, Any]:
        """Return model config as dict for model provider."""
        return {
            "model_type": self.model_type,
            "vocab_size": self.vocab_size,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "num_attention_heads": self.num_attention_heads,
            "seq_length": self.seq_length,
            "dropout": self.dropout,
        }

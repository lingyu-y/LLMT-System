"""Training schemas – request / response models for the training API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Privacy config
# ---------------------------------------------------------------------------

class PrivacyConfigRequest(BaseModel):
    epsilon: float = Field(..., ge=0.01, le=100.0, description="隐私预算 ε")
    delta: float = Field(default=1e-5, ge=0, le=1.0, description="隐私保证 δ")
    noise_multiplier: float = Field(default=1.0, ge=0, description="噪声乘数")
    max_grad_norm: float = Field(default=1.0, gt=0, description="梯度裁剪阈值")
    target_epsilon: float | None = Field(default=None, ge=0.01, le=100.0)
    target_delta: float | None = Field(default=None, ge=0, le=1.0)
    algorithm: str = Field(default="dp-sgd", description="差分隐私算法")


# ---------------------------------------------------------------------------
# Training config dict (embedded in create request)
# ---------------------------------------------------------------------------

class TrainingConfigDict(BaseModel):
    """Training hyper-params + model + strategy config, stored in config_json."""

    model_config = {"protected_namespaces": ()}

    # Model
    model_type: str = "gpt2"
    vocab_size: int = 50257
    hidden_size: int = 768
    num_layers: int = 12
    num_attention_heads: int = 12
    seq_length: int = 1024

    # Hyper-params
    batch_size: int = Field(default=32, description="Per-GPU micro batch size")
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    max_epochs: int = 10
    max_steps: int | None = None
    warmup_steps: int = 1000
    max_grad_norm: float = 1.0
    gradient_accumulation_steps: int = 1
    optimizer: Literal["adamw", "adam", "sgd", "adafactor"] = "adamw"
    scheduler: Literal["linear_warmup_decay", "cosine", "constant_warmup", "polynomial"] = "linear_warmup_decay"
    precision: Literal["fp16", "bf16", "fp32"] = "fp16"
    min_lr: float = 0.0
    beta1: float = 0.9
    beta2: float = 0.999

    # Data
    dataset_path: str | None = None
    dataset_format: Literal["jsonl", "parquet", "megatron_bin_idx", "npy"] = "jsonl"
    train_split: float = 0.95
    seed: int = 42

    # Strategy / parallelism
    num_gpus: int = 1
    num_nodes: int = 1
    tensor_model_parallel_size: int = 1
    pipeline_model_parallel_size: int = 1

    # Checkpoint
    save_interval: int = 500
    eval_interval: int = 100
    max_checkpoints: int = 5
    upload_to_minio: bool = True

    # Framework-specific overrides
    deepspeed_overrides: Optional[dict] = None
    megatron_overrides: Optional[dict] = None


# ---------------------------------------------------------------------------
# Create / update requests
# ---------------------------------------------------------------------------

class TrainingTaskCreate(BaseModel):
    """Request body for creating a new training task."""
    task_name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    dataset_id: int
    framework: Literal["pytorch", "deepspeed", "megatron"] = "deepspeed"
    parallel_strategy: Literal[
        "ddp", "zero1", "zero2", "zero3", "zero3_offload", "tp", "pp", "3d",
    ] = "zero2"
    config: TrainingConfigDict = Field(default_factory=TrainingConfigDict)


class SubmitTaskRequest(BaseModel):
    """Request body for submitting an existing created training task."""
    task_code: str = Field(..., min_length=1, max_length=64)


class ScaleTaskRequest(BaseModel):
    """Request body for scaling a running or paused training task."""
    gpu_count: int = Field(..., ge=1, le=64)
    parallel_strategy: Optional[str] = Field(default=None, max_length=64)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TrainingTaskOut(BaseModel):
    """Full training task response."""
    id: int
    task_name: str
    task_code: str
    description: Optional[str]
    status: str
    framework: Optional[str]
    parallel_strategy: Optional[str]
    config_json: dict[str, Any]
    current_epoch: int
    current_step: int
    max_epoch: Optional[int]
    dataset_id: int
    checkpoint_path: Optional[str]
    error_message: Optional[str]
    celery_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrainingTaskListOut(BaseModel):
    """Paginated list item with computed display fields."""
    id: int
    task_name: str
    task_code: str
    status: str
    framework: Optional[str]
    parallel_strategy: Optional[str]
    current_epoch: int
    current_step: int
    max_epoch: Optional[int]
    dataset_id: int
    config_json: dict[str, Any] = {}
    created_at: datetime
    # Computed display fields
    progress: int = 0
    gpu_display: str = ""

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Metrics query
# ---------------------------------------------------------------------------

class TrainingMetricsQuery(BaseModel):
    """Query parameters for fetching training metrics from InfluxDB."""
    task_code: str = ""
    metric_type: str = "training_step"
    start_time: str | None = None
    stop_time: str | None = None
    window: str = "10s"


# ---------------------------------------------------------------------------
# Options response
# ---------------------------------------------------------------------------

class OptionItem(BaseModel):
    value: str
    label: str


class DatasetOptionItem(BaseModel):
    value: int
    label: str


class TrainingOptionsOut(BaseModel):
    models: list[OptionItem] = []
    datasets: list[DatasetOptionItem] = []
    frameworks: list[OptionItem] = []
    gpu_options: list[OptionItem] = []
    parallel_strategies: list[OptionItem] = []

"""Training configuration Pydantic models – unified config for all frameworks."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

class ModelConfig(BaseModel):
    """Model architecture configuration."""

    model_config = {"protected_namespaces": ()}

    model_type: str = "gpt2"
    vocab_size: int = 50257
    hidden_size: int = 768
    num_layers: int = 12
    num_attention_heads: int = 12
    intermediate_size: int | None = None  # defaults to 4 * hidden_size
    seq_length: int = 1024
    max_position_embeddings: int | None = None
    dropout: float = 0.1
    layer_norm_eps: float = 1e-5
    activation: Literal["gelu", "gelu_new", "relu", "silu", "swiglu"] = "gelu_new"
    # BERT-specific
    type_vocab_size: int = 2
    # LLaMA-specific
    rms_norm_eps: float = 1e-6
    rope_theta: float = 10000.0
    use_cache: bool = True

    @model_validator(mode="after")
    def _set_defaults(self) -> "ModelConfig":
        if self.intermediate_size is None:
            self.intermediate_size = 4 * self.hidden_size
        if self.max_position_embeddings is None:
            self.max_position_embeddings = self.seq_length
        return self


class DataConfig(BaseModel):
    """Data loading configuration."""
    dataset_path: str = ""
    dataset_paths: list[str] = Field(default_factory=list)
    dataset_format: Literal["jsonl", "parquet", "megatron_bin_idx", "npy"] = "jsonl"
    train_split: float = 0.95
    seed: int = 42
    num_workers: int = 0
    pin_memory: bool = True
    shard_size_mb: int = 0


class HyperParamsConfig(BaseModel):
    """Training hyperparameters."""
    batch_size: int = Field(default=32, description="Per-GPU micro batch size")
    learning_rate: float = 2e-5
    min_lr: float = 0.0
    weight_decay: float = 0.01
    max_epochs: int = 10
    max_steps: int | None = None
    warmup_steps: int = 1000
    max_grad_norm: float = 1.0
    gradient_accumulation_steps: int = 1
    optimizer: Literal["adamw", "adam", "sgd", "adafactor"] = "adamw"
    scheduler: Literal["linear_warmup_decay", "cosine", "constant_warmup", "polynomial"] = "linear_warmup_decay"
    precision: Literal["fp16", "bf16", "fp32"] = "fp16"
    beta1: float = 0.9
    beta2: float = 0.999
    adam_epsilon: float = 1e-8
    lr_decay_iters: int | None = None


class StrategyConfig(BaseModel):
    """Parallelism and distributed training strategy."""
    num_gpus: int = 1
    num_nodes: int = 1
    tensor_model_parallel_size: int = 1
    pipeline_model_parallel_size: int = 1
    # DeepSpeed-specific
    zero_stage: int = Field(default=0, ge=0, le=3)
    zero_offload: bool = False
    zero_offload_params: bool = False
    overlap_comm: bool = True
    reduce_scatter: bool = True
    contiguous_gradients: bool = True
    # Activation checkpointing
    activation_checkpointing: bool = False
    partition_activations: bool = False
    cpu_checkpointing: bool = False

    @property
    def data_parallel_size(self) -> int:
        """Compute data parallel size from total GPUs / (TP * PP)."""
        tp = self.tensor_model_parallel_size
        pp = self.pipeline_model_parallel_size
        total = self.num_gpus * self.num_nodes
        return max(1, total // (tp * pp))


class CheckpointConfig(BaseModel):
    """Checkpointing configuration."""
    save_interval: int = 500
    eval_interval: int = 100
    max_checkpoints: int = 5
    upload_to_minio: bool = True
    checkpoint_dir: str = "./checkpoints"


class ReportingConfig(BaseModel):
    """Metrics reporting configuration."""
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = ""
    influxdb_org: str = "llmt"
    influxdb_bucket: str = "training_metrics"
    report_interval_steps: int = 10
    report_gpu_metrics: bool = True


# ---------------------------------------------------------------------------
# Unified config
# ---------------------------------------------------------------------------

class TrainingConfig(BaseModel):
    """Unified training configuration for all frameworks.

    This single config object is the source of truth. Framework-specific
    configs (DeepSpeed JSON, Megatron CLI args) are derived from it
    via ConfigMerger.
    """
    task_code: str = ""
    framework: Literal["pytorch", "deepspeed", "megatron"] = "deepspeed"
    parallel_strategy: Literal[
        "ddp", "zero1", "zero2", "zero3", "zero3_offload", "tp", "pp", "3d",
    ] = "zero2"

    model: ModelConfig = Field(default_factory=ModelConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    hyperparams: HyperParamsConfig = Field(default_factory=HyperParamsConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)

    # Framework-specific overrides (merged on top of generated config)
    deepspeed_overrides: Optional[dict] = None
    megatron_overrides: Optional[dict] = None

    @model_validator(mode="after")
    def _sync_strategy(self) -> "TrainingConfig":
        """Sync parallel_strategy into StrategyConfig fields."""
        s = self.strategy
        ps = self.parallel_strategy
        if ps == "ddp":
            s.zero_stage = 0
            s.zero_offload = False
        elif ps == "zero1":
            s.zero_stage = 1
        elif ps == "zero2":
            s.zero_stage = 2
        elif ps == "zero3":
            s.zero_stage = 3
        elif ps == "zero3_offload":
            s.zero_stage = 3
            s.zero_offload = True
            s.zero_offload_params = True
        elif ps == "tp":
            s.tensor_model_parallel_size = max(s.tensor_model_parallel_size, 2)
        elif ps == "pp":
            s.pipeline_model_parallel_size = max(s.pipeline_model_parallel_size, 2)
        elif ps == "3d":
            s.tensor_model_parallel_size = max(s.tensor_model_parallel_size, 2)
            s.pipeline_model_parallel_size = max(s.pipeline_model_parallel_size, 2)
        return self

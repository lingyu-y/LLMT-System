"""Training schemas."""

from pydantic import BaseModel, Field


class PrivacyConfigRequest(BaseModel):
    epsilon: float = Field(..., ge=0.01, le=100.0, description="隐私预算 ε")
    delta: float = Field(default=1e-5, ge=0, le=1.0, description="隐私保证 δ")
    noise_multiplier: float = Field(default=1.0, ge=0, description="噪声乘数")
    max_grad_norm: float = Field(default=1.0, gt=0, description="梯度裁剪阈值")
    target_epsilon: float | None = Field(default=None, ge=0.01, le=100.0)
    target_delta: float | None = Field(default=None, ge=0, le=1.0)
    algorithm: str = Field(default="dp-sgd", description="差分隐私算法")


class RecommendationRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(..., description="模型代码")
    dataset_id: int = Field(..., ge=1, description="数据集 ID")
    gpu_count: int = Field(..., ge=1, le=64, description="可用 GPU 数量")
    batch_size: int = Field(default=32, ge=1, description="每 GPU batch size")
    max_seq_length: int = Field(default=2048, ge=128, le=32768, description="最大序列长度")


class ConfigPreviewRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(...)
    dataset_id: int = Field(..., ge=1)
    gpu_count: int = Field(..., ge=1, le=64)
    framework: str = Field(default="PyTorch")
    parallel_strategy: str = Field(default="ddp")
    learning_rate: float = Field(default=1e-4, gt=0)
    batch_size: int = Field(default=32, ge=1)
    max_epoch: int = Field(default=3, ge=1, le=1000)
    max_seq_length: int = Field(default=2048, ge=128, le=32768)
    optimizer: str = Field(default="AdamW")
    scheduler: str = Field(default="cosine")
    warmup_steps: int = Field(default=500, ge=0)
    gradient_accumulation_steps: int = Field(default=1, ge=1)
    output_dir: str = Field(default="./output")


class SaveConfigRequest(ConfigPreviewRequest):
    task_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None


from datetime import datetime
from typing import Any


class TaskListOut(BaseModel):
    id: str
    taskName: str
    taskCode: str
    model: str
    datasetId: int
    framework: str | None = None
    parallelStrategies: list[str] = []
    gpu: str | None = None
    status: str
    progress: int = 0
    currentEpoch: int
    currentStep: int
    maxEpoch: int | None = None
    loss: float | None = None
    latency: int | None = None
    checkpointPath: str | None = None

    model_config = {"from_attributes": False}


class TaskOut(TaskListOut):
    id: str
    description: str | None = None
    configJson: dict[str, Any] = {}
    errorMessage: str | None = None
    startedAt: datetime | None = None
    endedAt: datetime | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    model_config = {"from_attributes": False}


class ScaleTaskRequest(BaseModel):
    gpu_count: int = Field(..., ge=1, le=64, description="目标 GPU 数量")
    parallel_strategy: str | None = Field(default=None, description="目标并行策略（可选）")


class SubmitTaskRequest(BaseModel):
    task_code: str = Field(..., description="训练配置的任务代码")


class LaunchCheckRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(...)
    dataset_id: int = Field(..., ge=1)
    gpu_count: int = Field(..., ge=1, le=64)

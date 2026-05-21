"""Model schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ModelMetrics(BaseModel):
    """结构化模型性能指标。"""
    accuracy_train: float | None = None
    accuracy_val: float | None = None
    f1_score: float | None = None
    precision: float | None = None
    recall: float | None = None
    loss_final: float | None = None
    inference_speed_ms: float | None = Field(default=None, description="单次推理耗时(毫秒)")
    latency_p99_ms: float | None = Field(default=None, description="P99延迟(毫秒)")
    loss_curve: list[dict[str, Any]] = Field(default_factory=list, description="[{step, loss}] 训练损失曲线")


class TrainingMetadata(BaseModel):
    """训练过程元数据。"""
    training_started_at: str | None = Field(default=None, description="训练开始时间 ISO 8601")
    training_duration_hours: float | None = Field(default=None, description="训练耗时(小时)")
    dataset_version: str | None = None
    data_source: str | None = Field(default=None, description="数据集来源/名称")
    learning_rate: float | None = None
    batch_size: int | None = None
    optimizer: str | None = None
    loss_function: str | None = None
    framework: str | None = Field(default=None, description="PyTorch/DeepSpeed/Megatron-LM")


class ModelCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., min_length=1, max_length=128)
    model_code: str = Field(..., min_length=1, max_length=64)
    tag: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    training_metadata: TrainingMetadata = Field(default_factory=TrainingMetadata)
    metrics: ModelMetrics = Field(default_factory=ModelMetrics)


class ModelImport(BaseModel):
    model_config = {"protected_namespaces": ()}

    source_path: str = Field(..., min_length=1, description="MinIO 中的源路径")
    model_name: str = Field(..., min_length=1, max_length=128)
    model_code: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=32)
    tag: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    framework: Optional[str] = Field(default=None, max_length=32)
    dataset_version: Optional[str] = Field(default=None, max_length=32)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    hyperparams_json: dict[str, Any] = Field(default_factory=dict)


class RateLimitUpdate(BaseModel):
    enabled: bool | None = None
    requests_per_minute: int | None = Field(default=None, ge=1)
    requests_per_hour: int | None = Field(default=None, ge=1)
    requests_per_day: int | None = Field(default=None, ge=1)
    concurrent: int | None = Field(default=None, ge=1)
    max_tokens_per_request: int | None = Field(default=None, ge=1)


class RollbackRequest(BaseModel):
    reason: str = Field(default="", max_length=512, description="回滚原因")


class ModelExport(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=32)
    target_path: str = Field(..., min_length=1, description="导出到 MinIO 的目标路径")


class VersionCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    version: str = Field(..., min_length=1, max_length=32)
    model_name: Optional[str] = Field(default=None, max_length=128)
    tag: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    framework: Optional[str] = Field(default=None, max_length=32)
    dataset_version: Optional[str] = Field(default=None, max_length=32)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    hyperparams_json: dict[str, Any] = Field(default_factory=dict)


class ModelListOut(BaseModel):
    id: int
    model_name: str
    model_code: str
    version: str
    tag: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    dataset_version: Optional[str] = None
    is_current: bool
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ModelOut(BaseModel):
    id: int
    model_name: str
    model_code: str
    version: str
    tag: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    metrics: ModelMetrics = Field(default_factory=ModelMetrics)
    training_metadata: TrainingMetadata = Field(default_factory=TrainingMetadata)
    storage_path: str = ""
    is_current: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}

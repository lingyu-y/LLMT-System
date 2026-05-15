"""Model schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ModelCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_name: str = Field(..., min_length=1, max_length=128)
    model_code: str = Field(..., min_length=1, max_length=64)
    version: str = Field(..., min_length=1, max_length=32)
    tag: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    framework: Optional[str] = Field(default=None, max_length=32)
    dataset_version: Optional[str] = Field(default=None, max_length=32)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    hyperparams_json: dict[str, Any] = Field(default_factory=dict)


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
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    hyperparams_json: dict[str, Any] = Field(default_factory=dict)
    dataset_version: Optional[str] = None
    is_current: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}

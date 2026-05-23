"""Dataset schemas for data processing management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DatasetOwnerOut(BaseModel):
    id: int
    username: str
    real_name: Optional[str]

    model_config = {"from_attributes": True}


class DatasetListOut(BaseModel):
    id: int
    name: str
    data_type: str
    version: str
    file_count: int
    total_size: int
    quality_status: str
    processing_status: str
    lineage_status: str
    source: Optional[str]
    owner: Optional[DatasetOwnerOut] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    data_type: str
    version: str
    source: Optional[str]
    storage_path: str
    file_count: int
    total_size: int
    quality_status: str
    processing_status: str
    lineage_status: str
    owner: Optional[DatasetOwnerOut] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(default=None)
    data_type: str = Field(..., min_length=1, max_length=32)
    version: str = Field(default="v1.0.0", max_length=32)
    source: Optional[str] = Field(default=None, max_length=255)
    storage_path: str = Field(default="/datasets", max_length=512)
    file_count: int = Field(default=0, ge=0)
    total_size: int = Field(default=0, ge=0)


class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None)
    data_type: Optional[str] = Field(default=None, max_length=32)
    version: Optional[str] = Field(default=None, max_length=32)
    source: Optional[str] = Field(default=None, max_length=255)
    storage_path: Optional[str] = Field(default=None, max_length=512)
    file_count: Optional[int] = Field(default=None, ge=0)
    total_size: Optional[int] = Field(default=None, ge=0)


# ============================================================================
# 处理任务 & 质量 & 血缘
# ============================================================================


class ProcessingJobOut(BaseModel):
    job_id: str
    dataset_id: int
    dataset_name: str
    job_type: str
    status: str
    progress: int
    output_path: Optional[str] = None
    record_count: Optional[int] = None
    processed_size: Optional[int] = None
    source_file_count: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[str]
    finished_at: Optional[str]


class QualityReportOut(BaseModel):
    dataset_id: int
    dataset_name: str
    overall_score: float
    completeness: bool
    consistency: bool
    timeliness: bool
    anomalies: list[dict] = []
    checked_at: Optional[str]


class LineageOut(BaseModel):
    dataset_id: int
    dataset_name: str
    source: Optional[str]
    transformations: list[str] = []
    upstream: list[str] = []
    downstream: list[str] = []


class ImpactOut(BaseModel):
    dataset_id: int
    affected_models: list[str] = []
    affected_tasks: list[str] = []
    affected_datasets: list[str] = []

"""Dashboard schemas (Part 2 of jiekou.md)."""

from typing import Optional

from pydantic import BaseModel


class SummaryOut(BaseModel):
    gpu_memory_used: float
    gpu_memory_total: float
    communication_latency_ms: float
    training_progress: float
    running_tasks: int
    gpu_utilization: float
    cpu_utilization: float
    updated_at: str


class MetricPoint(BaseModel):
    timestamp: str
    value: float


class MetricsOut(BaseModel):
    loss: list[MetricPoint] = []
    gpu_utilization: list[MetricPoint] = []
    latency: list[MetricPoint] = []


class TrainingTaskOut(BaseModel):
    task_id: str
    task_name: str
    model: str
    status: str
    progress: int
    current_epoch: int
    current_step: int
    loss: Optional[float]
    gpu: str


class ActivityOut(BaseModel):
    id: int
    username: str
    action: str
    resource: str
    detail: str
    created_at: str


class AlertOut(BaseModel):
    level: str
    message: str
    source: str
    created_at: str

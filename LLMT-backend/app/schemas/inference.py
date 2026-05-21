"""Model inference schemas (Part 6 of jiekou.md)."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InferenceModelOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_code: str
    model_name: str
    version: str
    framework: Optional[str] = None
    tag: Optional[str] = None


class PredictRequest(BaseModel):
    input: str = Field(..., min_length=1)
    parameters: dict = {}


class PredictResponse(BaseModel):
    model_code: str
    output: str
    latency_ms: float


class AsyncJobRequest(BaseModel):
    model_code: str
    input: str = Field(..., min_length=1)
    parameters: dict = {}


class AsyncJobOut(BaseModel):
    job_id: str
    model_code: str
    status: str
    input: str
    output: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None


class UsageOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_code: str
    total_calls: int
    remaining_calls: int
    limit_per_minute: int
    reset_at: str

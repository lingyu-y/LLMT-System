"""Document generation schemas (Part 7 of jiekou.md)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 文档生成模型
# ---------------------------------------------------------------------------


class DocumentModelOut(BaseModel):
    code: str
    name: str
    description: str


# ---------------------------------------------------------------------------
# 对话生成
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    prompt: str = Field(..., min_length=1)
    model_code: str = Field(default="default")
    context: Optional[str] = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    reply: str
    model_code: str


# ---------------------------------------------------------------------------
# 按类型生成
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    doc_type: str = Field(..., description="需求 | 设计 | 接口 | 用户手册")
    title: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    model_code: str = Field(default="default")
    template: Optional[str] = None


class GenerateResponse(BaseModel):
    draft_id: str
    doc_type: str
    title: str
    content: str
    generated_at: str


# ---------------------------------------------------------------------------
# 质量检查
# ---------------------------------------------------------------------------


class QualityCheckRequest(BaseModel):
    content: str = Field(..., min_length=1)


class QualityCheckResponse(BaseModel):
    score: float
    issues: list[str] = []
    suggestions: list[str] = []


# ---------------------------------------------------------------------------
# 草稿
# ---------------------------------------------------------------------------


class DraftCreate(BaseModel):
    doc_type: str = Field(..., max_length=64)
    title: str = Field(..., min_length=1, max_length=256)
    content: str = Field(default="")


class DraftUpdate(BaseModel):
    doc_type: Optional[str] = Field(default=None, max_length=64)
    title: Optional[str] = Field(default=None, max_length=256)
    content: Optional[str] = None


class DraftOut(BaseModel):
    id: str
    user_id: int
    doc_type: str
    title: str
    content: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# 导出/下载
# ---------------------------------------------------------------------------


class ExportResponse(BaseModel):
    draft_id: str
    format: str
    content: str

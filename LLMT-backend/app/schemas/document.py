"""Document schemas."""

from pydantic import BaseModel, Field


class DocumentChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(..., description="模型代码")
    message: str = Field(..., min_length=1, description="用户消息")


class DocumentGenerateRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(..., description="模型代码")
    doc_type: str = Field(..., description="文档类型: report/article/manual/summary/qa")
    title: str = Field(..., min_length=1, description="文档标题")
    outline: str | None = Field(default=None, description="大纲（可选）")
    requirements: str | None = Field(default=None, description="补充需求（可选）")


class QualityCheckRequest(BaseModel):
    content: str = Field(..., min_length=1, description="待检查的文档内容")


class DraftSaveRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_code: str = Field(...)
    doc_type: str = Field(...)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class DraftUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    content: str | None = Field(default=None, min_length=1)

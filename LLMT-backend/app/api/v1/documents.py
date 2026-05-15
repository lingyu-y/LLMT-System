"""Document generation endpoints -- 文档生成接口 (Part 7 of jiekou.md)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories import document_repository
from app.services import log_service
from app.schemas.document import (
    ChatRequest,
    DraftCreate,
    DraftUpdate,
    GenerateRequest,
    QualityCheckRequest,
)

router = APIRouter(prefix="/documents", tags=["文档生成"])

# ============================================================================
# 模型 & 生成
# ============================================================================


@router.get("/models")
def list_document_models(
    _current_user: User = Depends(get_current_user),
):
    models = document_repository.get_available_models()
    return success_response(models)


@router.post("/chat")
def chat_generate(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    result = document_repository.chat_generate(
        prompt=body.prompt, model_code=body.model_code, context=body.context,
    )
    return success_response(result, "对话生成完成")


@router.post("/generate")
def generate_by_type(
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
):
    result = document_repository.generate_by_type(
        doc_type=body.doc_type, title=body.title, prompt=body.prompt,
        model_code=body.model_code, template=body.template,
    )
    # 生成后自动保存为草稿（草稿 ID 已在 result 中）
    draft = document_repository.get_draft(result["draft_id"])
    if draft:
        draft["user_id"] = current_user.id
    return success_response(result, "文档生成完成")


@router.post("/quality-check")
def quality_check(
    body: QualityCheckRequest,
    _current_user: User = Depends(get_current_user),
):
    result = document_repository.check_quality(body.content)
    return success_response(result, "质量检查完成")


# ============================================================================
# 草稿 CRUD
# ============================================================================


@router.get("/drafts")
def list_drafts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    drafts, total = document_repository.get_drafts(
        current_user.id, page=page, page_size=page_size
    )
    return paginated_response(drafts, total, page, page_size)


@router.post("/drafts", status_code=status.HTTP_201_CREATED)
def create_draft(
    body: DraftCreate,
    current_user: User = Depends(get_current_user),
):
    draft = document_repository.create_draft(
        user_id=current_user.id,
        doc_type=body.doc_type,
        title=body.title,
        content=body.content,
    )
    return success_response(draft, "草稿保存成功")


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
):
    draft = document_repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    return success_response(draft)


@router.put("/drafts/{draft_id}")
def update_draft(
    draft_id: str,
    body: DraftUpdate,
    current_user: User = Depends(get_current_user),
):
    draft = document_repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    updated = document_repository.update_draft(draft_id, **body.model_dump(exclude_unset=True))
    return success_response(updated, "草稿修改成功")


@router.delete("/drafts/{draft_id}")
def delete_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
):
    if not document_repository.delete_draft(draft_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    return success_response(message="草稿删除成功")


# ============================================================================
# 导出 & 下载
# ============================================================================


@router.get("/{draft_id}/export")
def export_document(
    draft_id: str,
    fmt: str = Query("md", description="导出格式: md | html | pdf"),
    _current_user: User = Depends(get_current_user),
):
    result = document_repository.export_draft(draft_id, fmt=fmt)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return success_response(result, "导出成功")


@router.get("/{draft_id}/download")
def download_document(
    draft_id: str,
    _current_user: User = Depends(get_current_user),
):
    draft = document_repository.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return success_response(
        {"filename": f"{draft['title']}.md", "content": draft["content"], "size": len(draft["content"])},
        "下载就绪",
    )

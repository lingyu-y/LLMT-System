"""Document API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.responses import success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.document import DocumentChatRequest, DocumentGenerateRequest, DraftSaveRequest, DraftUpdateRequest, QualityCheckRequest

router = APIRouter(prefix="/documents", tags=["文档生成"])

DOCUMENT_MODELS = [
    {"value": "llama-7b-ft", "label": "LLaMA-7B Fine-tuned", "types": ["report", "summary", "manual"]},
    {"value": "bert-base", "label": "BERT-base-chinese", "types": ["classification", "extraction"]},
    {"value": "qwen-7b", "label": "Qwen-7B v2", "types": ["report", "article", "qa"]},
    {"value": "gpt2-distil", "label": "GPT-2 Distil Chinese", "types": ["article", "summary"]},
]


@router.get("/models")
def get_document_models():
    return success_response(DOCUMENT_MODELS)


@router.post("/chat")
def document_chat(
    body: DocumentChatRequest,
    current_user: User = Depends(get_current_user),
):
    valid_models = {m["value"] for m in DOCUMENT_MODELS}
    if body.model_code not in valid_models:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的文档生成模型")

    return success_response({
        "role": "assistant",
        "content": f"已收到您的消息：「{body.message}」。基于 {body.model_code} 模型，我将为您生成文档内容。请继续描述您的需求，或使用 /generate 直接生成。",
        "model_code": body.model_code,
    })


GENERATED_CONTENT = {
    "report": "# {title}\n\n## 摘要\n本文基于需求分析，系统阐述了{title}的核心架构与实现方案。\n\n## 背景\n随着业务规模的增长...\n\n## 方案设计\n### 架构概览\n采用微服务架构...\n\n## 总结\n本文档覆盖了{title}的完整设计方案。",
    "article": "# {title}\n\n## 引言\n{title}是当前技术领域的热门话题...\n\n## 核心内容\n经过深入分析...\n\n## 结论\n综上所述，{title}在未来将持续发展。",
    "manual": "# {title} 用户手册\n\n## 概述\n本文档为{title}的使用指南。\n\n## 快速开始\n### 环境准备\n...\n\n### 安装步骤\n...\n\n## 常见问题\n...",
    "summary": "# {title} 摘要\n\n## 核心要点\n- 要点一\n- 要点二\n\n## 详细总结\n...\n\n## 建议\n...",
    "qa": "# {title} Q&A\n\n## 常见问题\n**Q1:** ...\n**A1:** ...\n\n**Q2:** ...\n**A2:** ...",
}


@router.post("/generate")
def document_generate(
    body: DocumentGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    valid_models = {m["value"] for m in DOCUMENT_MODELS}
    if body.model_code not in valid_models:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的文档生成模型")

    model = next((m for m in DOCUMENT_MODELS if m["value"] == body.model_code), None)
    if body.doc_type not in model["types"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"该模型不支持 {body.doc_type} 类型")

    template = GENERATED_CONTENT.get(body.doc_type, GENERATED_CONTENT["report"])
    content = template.format(title=body.title)

    return success_response({
        "model_code": body.model_code,
        "doc_type": body.doc_type,
        "title": body.title,
        "content": content,
        "word_count": len(content),
    }, "文档生成成功")


@router.post("/quality-check")
def document_quality_check(
    body: QualityCheckRequest,
    current_user: User = Depends(get_current_user),
):
    text = body.content
    word_count = len(text)
    issues = []

    if word_count < 100:
        issues.append({"level": "warn", "item": "内容长度", "detail": "文档不足100字，建议补充内容"})
    if "##" not in text and "#" not in text:
        issues.append({"level": "info", "item": "结构层次", "detail": "未检测到 Markdown 标题，建议添加层级标题"})
    if "。" not in text and "\n" not in text:
        issues.append({"level": "warn", "item": "段落分隔", "detail": "缺少句号或换行，建议合理分段"})
    if len([c for c in text if '一' <= c <= '鿿']) < 30:
        issues.append({"level": "info", "item": "中文内容", "detail": "中文字符较少，请确认内容完整性"})

    score = max(60, 100 - len([i for i in issues if i["level"] == "warn"]) * 10 - len([i for i in issues if i["level"] == "info"]) * 3)

    return success_response({
        "score": min(score, 100),
        "word_count": word_count,
        "issues": issues,
        "passed": len([i for i in issues if i["level"] == "warn"]) == 0,
    })


# --- Drafts (in-memory storage) ---
import uuid
from datetime import datetime, timezone

_drafts: dict[str, dict] = {}


@router.get("/drafts")
def list_drafts(current_user: User = Depends(get_current_user)):
    user_drafts = [
        {
            "id": d["id"],
            "title": d["title"],
            "doc_type": d["doc_type"],
            "model_code": d["model_code"],
            "word_count": len(d["content"]),
            "updated_at": d["updated_at"],
        }
        for d in _drafts.values()
        if d["user_id"] == current_user.id
    ]
    return success_response(sorted(user_drafts, key=lambda x: x["updated_at"], reverse=True))


@router.post("/drafts")
def save_draft(
    body: DraftSaveRequest,
    current_user: User = Depends(get_current_user),
):
    draft_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    _drafts[draft_id] = {
        "id": draft_id,
        "user_id": current_user.id,
        "title": body.title,
        "doc_type": body.doc_type,
        "model_code": body.model_code,
        "content": body.content,
        "created_at": now,
        "updated_at": now,
    }
    return success_response(_drafts[draft_id], "草稿已保存")


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
):
    draft = _drafts.get(draft_id)
    if draft is None or draft["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    return success_response(draft)


@router.put("/drafts/{draft_id}")
def update_draft(
    draft_id: str,
    body: DraftUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    draft = _drafts.get(draft_id)
    if draft is None or draft["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    if body.title is not None:
        draft["title"] = body.title
    if body.content is not None:
        draft["content"] = body.content
    draft["updated_at"] = datetime.now(timezone.utc).isoformat()
    return success_response(draft, "草稿已更新")


@router.delete("/drafts/{draft_id}")
def delete_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
):
    draft = _drafts.get(draft_id)
    if draft is None or draft["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
    del _drafts[draft_id]
    return success_response(message="草稿已删除")


@router.get("/{doc_id}/export")
def export_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    draft = _drafts.get(doc_id)
    if draft is None or draft["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return success_response({
        "export_url": f"/exports/documents/{doc_id}.docx",
        "format": "docx",
        "message": "文档已导出为 DOCX 格式",
    })


@router.get("/{doc_id}/download")
def download_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    from urllib.parse import quote

    from fastapi.responses import PlainTextResponse

    draft = _drafts.get(doc_id)
    if draft is None or draft["user_id"] != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    filename = quote(draft["title"] + ".md")
    return PlainTextResponse(
        content=draft["content"],
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )

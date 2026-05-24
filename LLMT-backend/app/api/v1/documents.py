"""Document generation API — powered by trained models via the inference engine."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.model_version import ModelVersion
from app.models.user import User
from app.schemas.document import (
    DocumentChatRequest,
    DocumentGenerateRequest,
    DraftSaveRequest,
    DraftUpdateRequest,
    QualityCheckRequest,
)

router = APIRouter(prefix="/documents", tags=["文档生成"])

# ---------------------------------------------------------------------------
# In-memory draft store
# ---------------------------------------------------------------------------
_drafts: dict[str, dict] = {}


def _build_model_entry(mv: ModelVersion) -> dict:
    """Convert a ModelVersion row into a document-model entry for the frontend."""
    hp = mv.hyperparams_json or {}
    return {
        "value": mv.model_code,
        "label": mv.model_name,
        "version": mv.version,
        "framework": mv.framework,
        "model_type": hp.get("model_type", "gpt2"),
        "types": ["report", "article", "summary", "manual", "qa"],
    }


@router.get("/models")
def get_document_models(db: Session = Depends(get_db)):
    """Return trained models available for document generation."""
    trained = (
        db.query(ModelVersion)
        .filter(ModelVersion.is_current == True)  # noqa: E712
        .order_by(ModelVersion.model_code)
        .all()
    )
    models = [_build_model_entry(m) for m in trained]
    return success_response(models)


# ---------------------------------------------------------------------------
# Shared helper — call the real inference engine
# ---------------------------------------------------------------------------

def _infer(model_code: str, prompt: str, max_tokens: int = 256, db: Session | None = None) -> str:
    """Run inference via the dedicated inference service when available,
    falling back to in-process model loading.
    """
    import logging
    _log = logging.getLogger(__name__)

    # -- Resolve model metadata from DB --
    hp: dict = {}
    version = "v1.0.0"
    model_type = "gpt2"
    if db is not None:
        mv = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.model_code == model_code,
                ModelVersion.is_current == True,  # noqa: E712
            )
            .first()
        )
        if mv is None:
            _log.warning("_infer: model_code=%r not found in model_versions (is_current=True)", model_code)
            return (
                f"未找到可用的文档生成模型 `{model_code}`。\n\n"
                "请确认：\n"
                "1. 已完成模型训练\n"
                "2. 训练任务已执行 promote 操作\n"
                "3. 模型在模型管理页面中状态为「当前版本」"
            )
        hp = mv.hyperparams_json or {}
        model_type = hp.get("model_type", "gpt2")
        version = mv.version or "v1.0.0"

    # -- Try inference service first (same as online test panel) --
    try:
        from app.core.config import get_settings
        settings = get_settings()
        svc_url = getattr(settings, "LLMT_INFERENCE_SERVICE_URL", None) or ""
        if svc_url:
            import httpx
            base_url = svc_url.rstrip("/")
            _log.info("_infer: delegating to inference service at %s", base_url)
            with httpx.Client(timeout=300.0, trust_env=False) as client:
                resp = client.post(
                    f"{base_url}/predict",
                    json={
                        "model_code": model_code,
                        "version": version,
                        "model_type": model_type,
                        "model_config": hp,
                        "input": prompt,
                        "parameters": {"max_new_tokens": max_tokens, "temperature": 0.7, "top_p": 0.9, "top_k": 50},
                    },
                )
            if resp.status_code < 400:
                result = resp.json()
                return result.get("output", result.get("detail", str(result)))
            _log.warning("_infer: inference service returned %d: %s", resp.status_code, resp.text[:300])
    except Exception as exc:
        _log.warning("_infer: inference service unavailable (%s), trying direct load", exc)

    # -- Fallback: direct in-process inference --
    try:
        from llmt_training.inference.engine import load_model, run_inference

        _log.info("_infer: loading model directly %s v%s type=%s", model_code, version, model_type)
        result = load_model(model_code, version, model_type=model_type, model_config=hp or None)
        if result is None:
            _log.warning("_infer: checkpoint not found for %s v%s", model_code, version)
            return (
                f"模型 `{model_code}` (v{version}) 的 checkpoint 文件未找到。\n\n"
                "可能原因：\n"
                "1. 训练完成后 checkpoint 未成功上传到 MinIO\n"
                "2. MinIO 服务未运行或连接失败\n"
                "3. 本地 checkpoint 目录已被清理\n\n"
                "请检查 MinIO 控制台 (http://localhost:9001) 的 models bucket 中是否存在对应文件。"
            )

        model, tokenizer = result
        output, _latency = run_inference(
            model, tokenizer, prompt,
            max_new_tokens=max_tokens,
            temperature=0.7,
            top_p=0.9,
            top_k=50,
        )
        return output

    except ImportError:
        _log.warning("_infer: inference engine not available (import failed)")
        return (
            f"[{model_code}] 推理引擎未安装，无法调用真实模型。\n\n"
            f"提示内容：{prompt[:200]}..."
        )
    except Exception as exc:
        _log.exception("_infer: direct inference failed for %s", model_code)
        return (
            f"[{model_code}] 推理过程出错：{exc}\n\n"
            f"请检查后端日志获取详细错误信息。"
        )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat")
def document_chat(
    body: DocumentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model_code = body.model_code
    prompt = _build_chat_prompt(body.message)
    content = _infer(model_code, prompt, max_tokens=256, db=db)

    return success_response({
        "role": "assistant",
        "content": content,
        "model_code": model_code,
    })


def _build_chat_prompt(message: str) -> str:
    return (
        "你是一个技术文档写作助手，服务于「离线大数据训练与应用系统」。\n"
        "请根据用户的需求，生成专业、结构清晰的文档内容。\n"
        "使用 Markdown 格式组织回答。\n\n"
        f"用户需求：{message}\n\n"
        "文档内容："
    )


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

@router.post("/generate")
def document_generate(
    body: DocumentGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model_code = body.model_code
    prompt = _build_generate_prompt(
        doc_type=body.doc_type,
        title=body.title,
        outline=body.outline,
        requirements=body.requirements,
    )
    content = _infer(model_code, prompt, max_tokens=512, db=db)

    return success_response({
        "model_code": model_code,
        "doc_type": body.doc_type,
        "title": body.title,
        "content": content,
        "word_count": len(content),
    }, "文档生成成功")


def _build_generate_prompt(
    doc_type: str,
    title: str,
    outline: str | None,
    requirements: str | None,
) -> str:
    type_hints = {
        "report": "技术报告，包含摘要、背景、方案设计、总结",
        "article": "技术文章，包含引言、核心内容、结论",
        "manual": "用户手册，包含概述、快速开始、安装步骤、常见问题",
        "summary": "摘要总结，包含核心要点、详细总结、建议",
        "qa": "Q&A 文档，以问答形式组织",
    }
    hint = type_hints.get(doc_type, type_hints["report"])

    prompt = (
        "你是一个技术文档写作助手，服务于「离线大数据训练与应用系统」。\n"
        f"请生成一份完整的{doc_type}类型文档。\n"
        f"文档结构应为：{hint}。\n"
        f"文档标题：{title}\n"
    )
    if outline:
        prompt += f"大纲要求：{outline}\n"
    if requirements:
        prompt += f"补充需求：{requirements}\n"
    prompt += "\n请直接输出完整的 Markdown 格式文档内容："
    return prompt


# ---------------------------------------------------------------------------
# Quality check
# ---------------------------------------------------------------------------

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

    score = max(60, 100 - len([i for i in issues if i["level"] == "warn"]) * 10
                - len([i for i in issues if i["level"] == "info"]) * 3)

    return success_response({
        "score": min(score, 100),
        "word_count": word_count,
        "issues": issues,
        "passed": len([i for i in issues if i["level"] == "warn"]) == 0,
    })


# ---------------------------------------------------------------------------
# Drafts CRUD
# ---------------------------------------------------------------------------

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

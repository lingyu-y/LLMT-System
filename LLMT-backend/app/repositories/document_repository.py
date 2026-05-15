"""Document generation repository — mock LLM + in-memory draft store.

When a real LLM backend is available, replace the mock functions here.
The API layer stays unchanged.
"""

import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 可用的文档生成模型（模拟）
# ---------------------------------------------------------------------------

_DOC_MODELS = [
    {"code": "default", "name": "LLMT-DocGen-v1", "description": "通用文档生成模型，支持需求/设计/接口/用户手册"},
    {"code": "codegen", "name": "LLMT-CodeDoc-v1", "description": "专注代码相关文档（API文档、接口说明）"},
    {"code": "uml", "name": "LLMT-UML-v1", "description": "支持 UML 图表描述的文档生成模型"},
]

# ---------------------------------------------------------------------------
# 内存草稿存储
# ---------------------------------------------------------------------------

_drafts: dict[str, dict] = {}


def get_available_models() -> list[dict]:
    return _DOC_MODELS


def chat_generate(prompt: str, model_code: str = "default", context: str | None = None) -> dict:
    return {
        "reply": f"[{model_code}] 基于提示生成的文档片段：{prompt[:100]}...",
        "model_code": model_code,
    }


def generate_by_type(
    doc_type: str, title: str, prompt: str, model_code: str = "default", template: str | None = None
) -> dict:
    draft_id = str(uuid.uuid4())[:8]
    content = (
        f"# {title}\n\n"
        f"## 文档类型：{doc_type}\n\n"
        f"## 生成模型：{model_code}\n\n"
        f"## 内容\n\n"
        f"根据提示「{prompt}」生成的{doc_type}文档内容。\n\n"
        f"（完整内容将在接入 LLM 后自动生成）\n"
    )
    _drafts[draft_id] = {
        "id": draft_id, "user_id": 0, "doc_type": doc_type,
        "title": title, "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"draft_id": draft_id, "doc_type": doc_type, "title": title,
            "content": content, "generated_at": datetime.now(timezone.utc).isoformat()}


def check_quality(content: str) -> dict:
    issues: list[str] = []
    suggestions: list[str] = []
    score = 100.0
    if len(content) < 50:
        issues.append("内容过短")
        suggestions.append("建议补充更多细节")
        score -= 20
    if "##" not in content:
        issues.append("缺少 Markdown 标题结构")
        suggestions.append("建议使用 ## 标题组织内容")
        score -= 10
    return {"score": max(score, 0), "issues": issues, "suggestions": suggestions}


# ---------------------------------------------------------------------------
# 草稿 CRUD
# ---------------------------------------------------------------------------


def create_draft(user_id: int, doc_type: str, title: str, content: str) -> dict:
    draft_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()
    draft = {
        "id": draft_id, "user_id": user_id, "doc_type": doc_type,
        "title": title, "content": content,
        "created_at": now, "updated_at": now,
    }
    _drafts[draft_id] = draft
    return draft


def get_drafts(user_id: int, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    user_drafts = [d for d in _drafts.values() if d["user_id"] == user_id]
    user_drafts.sort(key=lambda d: d["created_at"], reverse=True)
    total = len(user_drafts)
    start = (page - 1) * page_size
    return user_drafts[start : start + page_size], total


def get_draft(draft_id: str) -> dict | None:
    return _drafts.get(draft_id)


def update_draft(draft_id: str, **kwargs) -> dict | None:
    draft = _drafts.get(draft_id)
    if draft is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            draft[key] = value
    draft["updated_at"] = datetime.now(timezone.utc).isoformat()
    return draft


def delete_draft(draft_id: str) -> bool:
    if draft_id in _drafts:
        del _drafts[draft_id]
        return True
    return False


def export_draft(draft_id: str, fmt: str = "md") -> dict | None:
    draft = _drafts.get(draft_id)
    if draft is None:
        return None
    return {"draft_id": draft_id, "format": fmt, "content": draft["content"]}

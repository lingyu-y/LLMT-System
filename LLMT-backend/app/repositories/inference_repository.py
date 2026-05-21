"""Model inference repository — mock inference engine + async job store."""

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.model_version import ModelVersion

# ---------------------------------------------------------------------------
# In-memory async job store
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# 可推理模型列表（查询 model_versions 表）
# ---------------------------------------------------------------------------


def get_inference_models(db: Session) -> list[dict]:
    models = (
        db.query(ModelVersion)
        .filter(ModelVersion.is_current == True)  # noqa: E712
        .order_by(ModelVersion.model_code)
        .all()
    )
    return [
        {
            "model_code": m.model_code,
            "model_name": m.model_name,
            "version": m.version,
            "framework": m.framework,
            "tag": m.tag,
        }
        for m in models
    ]


# ---------------------------------------------------------------------------
# 同步推理（模拟）
# ---------------------------------------------------------------------------


def predict_sync(db: Session, model_code: str, input_text: str, parameters: dict) -> dict:
    model = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_code == model_code, ModelVersion.is_current == True)  # noqa: E712
        .first()
    )
    if model is None:
        return None
    start = time.perf_counter()
    output = f"[{model_code}] 推理结果: 基于输入「{input_text[:80]}」生成的预测输出。"
    latency = round((time.perf_counter() - start) * 1000, 2)
    return {"model_code": model_code, "output": output, "latency_ms": latency}


# ---------------------------------------------------------------------------
# 异步推理任务
# ---------------------------------------------------------------------------


def create_async_job(model_code: str, input_text: str, parameters: dict) -> dict:
    job_id = f"INF-{str(uuid.uuid4())[:8]}"
    job = {
        "job_id": job_id,
        "model_code": model_code,
        "status": "queued",
        "input": input_text,
        "output": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    _jobs[job_id] = job
    return job


def get_async_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def cancel_async_job(job_id: str) -> bool:
    job = _jobs.get(job_id)
    if job is None:
        return False
    if job["status"] in ("queued", "running"):
        job["status"] = "cancelled"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        return True
    return False


# ---------------------------------------------------------------------------
# 调用量/限流
# ---------------------------------------------------------------------------


def get_usage(model_code: str | None = None) -> list[dict]:
    return [
        {
            "model_code": model_code or "default",
            "total_calls": 1000,
            "remaining_calls": 850,
            "limit_per_minute": 100,
            "reset_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

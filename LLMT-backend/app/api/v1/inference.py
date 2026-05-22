"""Model inference endpoints — 模型推理接口 (Part 6 of jiekou.md)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.rate_limit import (
    check_rate_limit,
    extract_rate_limit_key,
    rate_limit_headers,
)
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories import inference_repository

router = APIRouter(prefix="/inference", tags=["模型推理"])

# 推理接口限流配置
INFERENCE_RATE_LIMIT = 60  # 次/分钟
INFERENCE_RATE_WINDOW = 60  # 秒


def _check_inference_rate_limit(
    request: Request,
    current_user: User,
) -> dict:
    """推理接口限流检查。"""
    key = extract_rate_limit_key(request, current_user.id)
    allowed, info = check_rate_limit(key, INFERENCE_RATE_LIMIT, INFERENCE_RATE_WINDOW)
    if not allowed:
        from app.core.rate_limit import rate_limit_http_exception
        raise rate_limit_http_exception(info)
    return info


@router.get("/models")
def list_inference_models(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    models = inference_repository.get_inference_models(db)
    return success_response(models)


@router.post("/models/{model_code}/predict")
def predict_sync(
    model_code: str,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 步骤 1-6: 滑动窗口限流检查
    rate_info = _check_inference_rate_limit(request, current_user)

    result = inference_repository.predict_sync(
        db, model_code=model_code,
        input_text=body.get("input", ""),
        parameters=body.get("parameters", {}),
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在或不可用")

    # 构造响应 + 注入限流响应头
    return JSONResponse(
        content={"message": "推理完成", "data": result},
        headers=rate_limit_headers(rate_info),
    )


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_async_job(
    body: dict,
    _current_user: User = Depends(get_current_user),
):
    job = inference_repository.create_async_job(
        model_code=body.get("model_code", "default"),
        input_text=body.get("input", ""),
        parameters=body.get("parameters", {}),
    )
    return success_response(job, "异步推理任务已创建")


@router.get("/jobs/{job_id}")
def get_async_job(
    job_id: str,
    _current_user: User = Depends(get_current_user),
):
    job = inference_repository.get_async_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return success_response(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_async_job(
    job_id: str,
    _current_user: User = Depends(get_current_user),
):
    if not inference_repository.cancel_async_job(job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在或不可取消")
    return success_response(message="任务已取消")


@router.get("/usage")
def get_usage(
    model_code: str = Query("", description="模型代码，空则返回全部"),
    _current_user: User = Depends(get_current_user),
):
    return success_response(inference_repository.get_usage(model_code or None))

"""Model inference endpoints — 模型推理接口 (Part 6 of jiekou.md)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.responses import success_response
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
settings = get_settings()

DEFAULT_INFERENCE_RATE_LIMIT = 100  # 次/分钟
INFERENCE_RATE_WINDOW = 60  # 秒


def _check_inference_rate_limit(
    request: Request,
    current_user: User,
    model,
    db: Session,
) -> dict:
    """推理接口限流检查。"""
    hyperparams = model.hyperparams_json or {}
    stored = hyperparams.get("rate_limit") or {}
    if stored.get("enabled", True) is False:
        return {
            "limit": 0,
            "remaining": 0,
            "current": 0,
            "window_seconds": INFERENCE_RATE_WINDOW,
            "retry_after_seconds": 0,
            "disabled": True,
        }

    limits = stored.get("limits") or {}
    requests_per_minute = int(limits.get("requests_per_minute") or DEFAULT_INFERENCE_RATE_LIMIT)
    key = extract_rate_limit_key(request, current_user.id)
    allowed, info = check_rate_limit(key, requests_per_minute, INFERENCE_RATE_WINDOW)
    if not allowed:
        from app.core.rate_limit import rate_limit_http_exception
        try:
            from app.services import log_service
            log_service.create_log(
                db,
                user_id=current_user.id,
                username=current_user.username,
                action="rate_limit_exceeded",
                resource="inference",
                resource_id=model.id,
                detail=(
                    f"模型 {model.model_code}:{model.version} 推理请求超限，"
                    f"{info['current']}/{info['limit']} 次/{info['window_seconds']}秒"
                ),
            )
        except Exception:
            pass
        raise rate_limit_http_exception(info)
    return info


@router.get("/models")
def list_inference_models(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    models = inference_repository.get_inference_models(db)
    return success_response(models)


@router.post("/models/{model_ref}/predict")
def predict_sync(
    model_ref: str,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    input_text = body.get("input", "")
    params = body.get("parameters", {})

    # Look up model metadata from DB
    from app.models.model_version import ModelVersion
    mv = db.query(ModelVersion).filter(
        ModelVersion.model_code == model_ref,
        ModelVersion.is_current == True,
    ).first()
    if mv is None and model_ref.isdigit():
        # Fallback: numeric refs from older frontend builds that used the DB id
        mv = db.query(ModelVersion).filter(ModelVersion.id == int(model_ref)).first()
    if mv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在或不可用")

    rate_info = _check_inference_rate_limit(request, current_user, mv, db)

    # Extract model type & config from stored hyperparams
    hyper = dict(mv.hyperparams_json or {})
    if hyper.get("tokenizer_type") is None and int(hyper.get("vocab_size", 50257) or 50257) != 50257:
        hyper["tokenizer_type"] = "sentencepiece"
        hyper.setdefault("tokenizer_path", "tokenizers/industry_spm.model")
    model_code = mv.model_code
    model_type = hyper.get("model_type", "gpt2")
    version = mv.version or "v1.0.0"

    # Load model + run real inference
    try:
        if settings.LLMT_INFERENCE_SERVICE_URL:
            base_url = settings.LLMT_INFERENCE_SERVICE_URL.rstrip("/")
            with httpx.Client(timeout=300.0, trust_env=False) as client:
                response = client.post(
                    f"{base_url}/predict",
                    json={
                        "model_code": model_code,
                        "version": version,
                        "model_type": model_type,
                        "model_config": hyper,
                        "input": input_text,
                        "parameters": params,
                    },
                )
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise HTTPException(status_code=response.status_code, detail=detail)
            result = response.json()
            result.setdefault("model_id", mv.id)
            result.setdefault("version", version)
            result.setdefault("model_config", hyper)
        else:
            from llmt_training.inference.engine import load_model, run_inference

            model_tok = load_model(model_code, version, model_type=model_type,
                                  model_config=hyper)
            if model_tok is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="无法加载模型权重，请确认 MinIO 中 checkpoint 存在",
                )

            model, tokenizer = model_tok
            max_new_tokens = int(params.get("max_new_tokens", 20))
            max_new_tokens = max(1, min(max_new_tokens, 64))
            output_text, latency_ms = run_inference(
                model, tokenizer, input_text,
                max_new_tokens=max_new_tokens,
                temperature=float(params.get("temperature", 0.7)),
                top_p=float(params.get("top_p", 0.85)),
                top_k=int(params.get("top_k", 20)),
            )
            result = {
                "model_code": model_code,
                "model_id": mv.id,
                "version": version,
                "output": output_text,
                "latency_ms": latency_ms,
                "input": input_text,
                "tokenizer": tokenizer.__class__.__name__,
                "vocab_size": getattr(tokenizer, "vocab_size", None),
                "model_config": hyper,
            }
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"推理服务不可用: {exc}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        import logging
        _log = logging.getLogger(__name__)
        _log.exception("Inference failed for %s", model_code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"推理失败: {exc}",
        )

    return JSONResponse(
        content={"message": "推理完成", "data": result},
        headers=rate_limit_headers(rate_info) if not rate_info.get("disabled") else {},
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

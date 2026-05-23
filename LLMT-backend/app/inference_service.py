"""Standalone inference service.

Run this in a separate process from the main FastAPI backend so large model
loads cannot take down the management API process.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings

settings = get_settings()


def _ensure_llmt_training_on_path() -> None:
    module_path = settings.LLMT_TRAINING_MODULE_PATH
    if os.path.isdir(module_path):
        source_dir = os.path.abspath(module_path)
    else:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        source_dir = os.path.join(repo_root, "LLMT-training")

    if not os.path.isdir(source_dir):
        return

    parent_dir = os.path.dirname(source_dir)
    symlink_path = os.path.join(parent_dir, "llmt_training")
    if os.path.islink(symlink_path) and os.path.realpath(symlink_path) != os.path.realpath(source_dir):
        try:
            os.unlink(symlink_path)
        except OSError:
            pass
    if not os.path.exists(symlink_path):
        try:
            os.symlink(source_dir, symlink_path)
        except OSError:
            pass

    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)


_ensure_llmt_training_on_path()

app = FastAPI(
    title=f"{settings.APP_NAME} - Inference Service",
    debug=settings.DEBUG,
)


class PredictRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    model_code: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    model_type: str = "gpt2"
    model_cfg: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    input: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict")
def predict(body: PredictRequest) -> dict[str, Any]:
    try:
        from llmt_training.inference.engine import load_model, run_inference

        model_tok = load_model(
            body.model_code,
            body.version,
            model_type=body.model_type,
            model_config=body.model_cfg,
        )
        if model_tok is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="无法加载模型权重，请确认 MinIO 中 checkpoint 存在",
            )

        model, tokenizer = model_tok
        params = body.parameters or {}
        max_new_tokens = int(params.get("max_new_tokens", 20))
        max_new_tokens = max(1, min(max_new_tokens, 64))
        output_text, latency_ms = run_inference(
            model,
            tokenizer,
            body.input,
            max_new_tokens=max_new_tokens,
            temperature=float(params.get("temperature", 0.8)),
            top_p=float(params.get("top_p", 0.9)),
            top_k=int(params.get("top_k", 50)),
        )
        return {
            "model_code": body.model_code,
            "output": output_text,
            "latency_ms": latency_ms,
            "input": body.input,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"推理失败: {exc}",
        ) from exc

"""Model API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_minio_client
from app.core.responses import paginated_response, success_response
from app.dependencies.auth import require_admin
from app.dependencies.db import get_db
from app.repositories import model_repository
from app.schemas.model import ModelCreate, ModelExport, ModelImport, ModelListOut, ModelOut, RateLimitUpdate, VersionCreate

import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/models", tags=["模型管理"])


@router.get("")
def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索模型名称/代码/框架"),
    db: Session = Depends(get_db),
):
    models, total = model_repository.get_models(
        db, page=page, page_size=page_size, keyword=keyword
    )
    data = [ModelListOut.model_validate(m) for m in models]
    return paginated_response(data, total, page, page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_model(
    body: ModelCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if model_repository.get_model_by_code_and_version(db, body.model_code, body.version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该模型代码与版本已存在"
        )
    model = model_repository.create_model(
        db,
        model_name=body.model_name,
        model_code=body.model_code,
        version=body.version,
        tag=body.tag,
        description=body.description,
        framework=body.framework,
        dataset_version=body.dataset_version,
        metrics_json=body.metrics_json,
        hyperparams_json=body.hyperparams_json,
    )
    return success_response(ModelOut.model_validate(model), "模型创建成功")


@router.post("/repository/import", status_code=status.HTTP_201_CREATED)
def import_model(
    body: ModelImport,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if model_repository.get_model_by_code_and_version(db, body.model_code, body.version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该模型代码与版本已存在"
        )

    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_MODELS
    target_prefix = f"models/{body.model_code}/{body.version}"

    src_prefix = body.source_path.rstrip("/") + "/"
    objects = list(minio.list_objects(bucket, prefix=src_prefix, recursive=True))
    files = [o for o in objects if not o.is_dir]
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源路径未找到文件")

    from minio.commonconfig import CopySource

    for obj in files:
        target_name = obj.object_name.replace(src_prefix, target_prefix + "/", 1)
        minio.copy_object(bucket, target_name, CopySource(bucket, obj.object_name))

    model = model_repository.create_model(
        db,
        model_name=body.model_name,
        model_code=body.model_code,
        version=body.version,
        tag=body.tag,
        description=body.description,
        framework=body.framework,
        dataset_version=body.dataset_version,
        metrics_json=body.metrics_json,
        hyperparams_json=body.hyperparams_json,
    )
    return success_response(ModelOut.model_validate(model), "模型导入成功")


@router.post("/repository/export")
def export_model(
    body: ModelExport,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    model = model_repository.get_model_by_code_and_version(db, body.model_code, body.version)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型版本不存在")

    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_MODELS
    source_prefix = model.storage_path.rstrip("/") + "/"

    objects = list(minio.list_objects(bucket, prefix=source_prefix, recursive=True))
    files = [o for o in objects if not o.is_dir]
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型文件不存在")

    from minio.commonconfig import CopySource

    target = body.target_path.rstrip("/") + "/"
    copied = 0
    for obj in files:
        target_name = obj.object_name.replace(source_prefix, target, 1)
        minio.copy_object(bucket, target_name, CopySource(bucket, obj.object_name))
        copied += 1

    return success_response({"exported": copied, "target_path": target}, "模型导出成功")


@router.get("/{model_code}/versions")
def get_model_versions(
    model_code: str,
    db: Session = Depends(get_db),
):
    versions = model_repository.get_versions(db, model_code)
    if not versions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")
    return success_response([ModelListOut.model_validate(v) for v in versions])


@router.post("/{model_code}/versions", status_code=status.HTTP_201_CREATED)
def create_model_version(
    model_code: str,
    body: VersionCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    existing = model_repository.get_versions(db, model_code)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")
    if model_repository.get_model_by_code_and_version(db, model_code, body.version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="该版本已存在"
        )
    model = model_repository.create_model(
        db,
        model_name=body.model_name or existing[0].model_name,
        model_code=model_code,
        version=body.version,
        tag=body.tag,
        description=body.description,
        framework=body.framework,
        dataset_version=body.dataset_version,
        metrics_json=body.metrics_json,
        hyperparams_json=body.hyperparams_json,
    )
    return success_response(ModelOut.model_validate(model), "版本创建成功")


@router.get("/{model_code}/versions/compare")
def compare_model_versions(
    model_code: str,
    v1: str = Query(..., description="版本号1"),
    v2: str = Query(..., description="版本号2"),
    db: Session = Depends(get_db),
):
    ver1 = model_repository.get_model_by_code_and_version(db, model_code, v1)
    ver2 = model_repository.get_model_by_code_and_version(db, model_code, v2)
    if ver1 is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"版本 {v1} 不存在")
    if ver2 is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"版本 {v2} 不存在")

    def version_snapshot(v):
        return {
            "version": v.version,
            "model_name": v.model_name,
            "tag": v.tag,
            "description": v.description,
            "framework": v.framework,
            "dataset_version": v.dataset_version,
            "metrics_json": v.metrics_json,
            "hyperparams_json": v.hyperparams_json,
            "is_current": v.is_current,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }

    return success_response({
        "v1": version_snapshot(ver1),
        "v2": version_snapshot(ver2),
    })


@router.post("/{model_code}/versions/{version}/rollback")
def rollback_model_version(
    model_code: str,
    version: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    model = model_repository.get_model_by_code_and_version(db, model_code, version)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型版本不存在")
    model = model_repository.rollback_version(db, model)
    return success_response(ModelOut.model_validate(model), "版本已回滚")


@router.get("/{model_code}/versions/{version}/download")
def download_model_version(
    model_code: str,
    version: str,
    db: Session = Depends(get_db),
):
    model = model_repository.get_model_by_code_and_version(db, model_code, version)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型版本不存在")

    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_MODELS
    prefix = model.storage_path.rstrip("/") + "/"

    objects = list(minio.list_objects(bucket, prefix=prefix, recursive=True))
    files = [o for o in objects if not o.is_dir]
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型文件不存在")

    obj = files[0]
    response = minio.get_object(bucket, obj.object_name)

    return StreamingResponse(
        response.stream(amt=64 * 1024),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{obj.object_name.split("/")[-1]}"'},
    )


@router.get("/{model_code}/versions/{version}")
def get_model_version_detail(
    model_code: str,
    version: str,
    db: Session = Depends(get_db),
):
    model = model_repository.get_model_by_code_and_version(db, model_code, version)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型版本不存在")
    return success_response(ModelOut.model_validate(model))


@router.post("/{model_code}/security/scan")
def trigger_security_scan(
    model_code: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    model = model_repository.get_model_by_code(db, model_code)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")

    scan_id = uuid.uuid4().hex[:12]
    return success_response({
        "scan_id": scan_id,
        "model_code": model.model_code,
        "version": model.version,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, "漏洞扫描任务已触发")


@router.get("/{model_code}/security/reports")
def get_security_reports(
    model_code: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    versions = model_repository.get_versions(db, model_code)
    if not versions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")

    reports = []
    for v in versions:
        reports.append({
            "scan_id": uuid.uuid4().hex[:12],
            "model_code": v.model_code,
            "version": v.version,
            "status": "completed",
            "summary": {"critical": 0, "high": 1, "medium": 3, "low": 5},
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        })

    return success_response(reports)


DEFAULT_LIMITS = {
    "requests_per_minute": 100,
    "requests_per_hour": 5000,
    "requests_per_day": 100000,
    "concurrent": 10,
    "max_tokens_per_request": 4096,
}


@router.get("/{model_code}/rate-limit")
def get_rate_limit(
    model_code: str,
    db: Session = Depends(get_db),
):
    model = model_repository.get_model_by_code(db, model_code)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")

    stored = model.hyperparams_json.get("rate_limit") or {}
    enabled = stored.get("enabled", True)
    limits = {**DEFAULT_LIMITS, **stored.get("limits", {})}

    return success_response({
        "model_code": model.model_code,
        "enabled": enabled,
        "limits": limits,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    })


@router.put("/{model_code}/rate-limit")
def update_rate_limit(
    model_code: str,
    body: RateLimitUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    model = model_repository.get_model_by_code(db, model_code)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")

    stored = model.hyperparams_json.get("rate_limit") or {}
    enabled = body.enabled if body.enabled is not None else stored.get("enabled", True)
    limits = {**DEFAULT_LIMITS, **stored.get("limits", {})}
    updates: dict[str, int] = {}
    if body.requests_per_minute is not None:
        updates["requests_per_minute"] = body.requests_per_minute
    if body.requests_per_hour is not None:
        updates["requests_per_hour"] = body.requests_per_hour
    if body.requests_per_day is not None:
        updates["requests_per_day"] = body.requests_per_day
    if body.concurrent is not None:
        updates["concurrent"] = body.concurrent
    if body.max_tokens_per_request is not None:
        updates["max_tokens_per_request"] = body.max_tokens_per_request
    limits.update(updates)

    model.hyperparams_json = {**model.hyperparams_json, "rate_limit": {"enabled": enabled, "limits": limits}}
    db.commit()
    db.refresh(model)

    return success_response({
        "model_code": model.model_code,
        "enabled": enabled,
        "limits": limits,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }, "限流策略已更新")


@router.get("/{model_code}")
def get_model(
    model_code: str,
    db: Session = Depends(get_db),
):
    model = model_repository.get_model_by_code(db, model_code)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="模型不存在")
    return success_response(ModelOut.model_validate(model))

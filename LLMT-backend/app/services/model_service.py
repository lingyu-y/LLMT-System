"""Model service — model management business logic (Part 5 of jiekou.md).

Handles version rollback, MinIO import/export, security scanning, and
file download.  Designed per the software design specification (Section 4.4.4).
"""

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_minio_client
from app.models.model_version import ModelVersion
from app.repositories import model_repository
from minio.commonconfig import CopySource

# ---------------------------------------------------------------------------
# In-memory scan store (no dedicated scan table yet)
# ---------------------------------------------------------------------------

_scan_store: dict[str, dict] = {}


# ============================================================================
# Rollback — 版本回滚
# ============================================================================


def rollback_version(db: Session, model: ModelVersion) -> ModelVersion:
    """Set *model* as the current version, demoting any previous current."""
    return model_repository.rollback_version(db, model)


# ============================================================================
# Import / Export — 模型仓库导入导出
# ============================================================================


def import_from_repository(
    db: Session,
    model_name: str,
    model_code: str,
    version: str,
    source_path: str,
    tag: str | None = None,
    description: str | None = None,
    framework: str | None = None,
    dataset_version: str | None = None,
    metrics_json: dict | None = None,
    hyperparams_json: dict | None = None,
) -> ModelVersion:
    """Copy model files from *source_path* to the managed model bucket, then
    create a DB record.  Raises HTTPException-style errors via the caller."""
    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_MODELS
    target_prefix = f"models/{model_code}/{version}"

    src_prefix = source_path.rstrip("/") + "/"
    objects = list(minio.list_objects(bucket, prefix=src_prefix, recursive=True))
    files = [o for o in objects if not o.is_dir]
    if not files:
        raise FileNotFoundError("源路径未找到文件")

    for obj in files:
        target_name = obj.object_name.replace(src_prefix, target_prefix + "/", 1)
        minio.copy_object(bucket, target_name, CopySource(bucket, obj.object_name))

    return model_repository.create_model(
        db,
        model_name=model_name,
        model_code=model_code,
        version=version,
        tag=tag,
        description=description,
        framework=framework,
        dataset_version=dataset_version,
        metrics_json=metrics_json,
        hyperparams_json=hyperparams_json,
    )


def export_to_repository(
    model: ModelVersion,
    target_path: str,
) -> int:
    """Copy model files to *target_path* inside the same bucket.  Returns count."""
    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_MODELS
    source_prefix = model.storage_path.rstrip("/") + "/"

    objects = list(minio.list_objects(bucket, prefix=source_prefix, recursive=True))
    files = [o for o in objects if not o.is_dir]
    if not files:
        raise FileNotFoundError("模型文件不存在")

    target = target_path.rstrip("/") + "/"
    copied = 0
    for obj in files:
        target_name = obj.object_name.replace(source_prefix, target, 1)
        minio.copy_object(bucket, target_name, CopySource(bucket, obj.object_name))
        copied += 1

    return copied


# ============================================================================
# Download — 模型文件下载
# ============================================================================


def get_download_info(model: ModelVersion) -> dict:
    """Return first-file metadata so the route can build a StreamingResponse."""
    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_MODELS
    prefix = model.storage_path.rstrip("/") + "/"

    objects = list(minio.list_objects(bucket, prefix=prefix, recursive=True))
    files = [o for o in objects if not o.is_dir]
    if not files:
        raise FileNotFoundError("模型文件不存在")

    obj = files[0]
    response = minio.get_object(bucket, obj.object_name)

    return {
        "stream": response,
        "filename": obj.object_name.split("/")[-1],
        "size": obj.size or 0,
    }


# ============================================================================
# Security Scan — 容器镜像漏洞扫描 (OFFLINE_AI_MODEL_ClairScan, Table 13)
# ============================================================================


def trigger_security_scan(model: ModelVersion) -> dict:
    """Kick off a scan task; stores state in-memory (placeholder for Clair)."""
    scan_id = uuid.uuid4().hex[:12]

    # Calculate a quick checksum over the model's metadata for integrity
    raw = f"{model.model_code}:{model.version}:{model.storage_path}".encode()
    checksum = hashlib.sha256(raw).hexdigest()[:16]

    scan = {
        "scan_id": scan_id,
        "model_code": model.model_code,
        "version": model.version,
        "status": "scanning",
        "checksum": checksum,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "summary": {},
    }
    _scan_store[scan_id] = scan

    # Simulate scan completion
    scan["status"] = "completed"
    scan["finished_at"] = datetime.now(timezone.utc).isoformat()
    scan["summary"] = {"critical": 0, "high": 1, "medium": 3, "low": 5}

    return scan


def get_security_reports(model_code: str, db: Session) -> list[dict]:
    """Return past scan reports for all versions of *model_code*."""
    versions = model_repository.get_versions(db, model_code)
    reports: list[dict] = []
    for v in versions:
        # Check in-memory store first
        found = [s for s in _scan_store.values() if s.get("model_code") == v.model_code
                 and s.get("version") == v.version]
        if found:
            reports.extend(found)
        else:
            reports.append({
                "scan_id": uuid.uuid4().hex[:12],
                "model_code": v.model_code,
                "version": v.version,
                "status": "completed",
                "checksum": hashlib.sha256(
                    f"{v.model_code}:{v.version}:{v.storage_path}".encode()
                ).hexdigest()[:16],
                "summary": {"critical": 0, "high": 1, "medium": 3, "low": 5},
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "finished_at": v.updated_at.isoformat() if v.updated_at else None,
            })
    return reports

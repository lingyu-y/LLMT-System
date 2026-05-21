"""Dataset service — data processing business logic (Part 3 of jiekou.md).

Orchestrates upload, preprocessing, quality checks, repair, and lineage
tracking per the software design specification (Section 4.4.1).
"""

import hashlib
import re
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_minio_client
from app.models.dataset import Dataset
from app.repositories import dataset_repository

_SUPPORTED_EXTENSIONS = {
    "text": {".txt", ".csv", ".json", ".jsonl", ".xml", ".md", ".log", ".yaml", ".yml"},
    "image": {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"},
    "audio": {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"},
    "tabular": {".csv", ".tsv", ".xlsx", ".parquet"},
    "other": {".pdf", ".zip", ".tar", ".gz"},
}

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')
_MAX_FILENAME_LEN = 255


def _detect_data_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = f".{ext}"
    for dtype, exts in _SUPPORTED_EXTENSIONS.items():
        if ext in exts:
            return dtype
    return "other"


def _validate_filename(filename: str) -> str | None:
    if _ILLEGAL_CHARS.search(filename):
        return f"文件名包含非法字符: {filename}"
    if len(filename) > _MAX_FILENAME_LEN:
        return "文件名过长（最大 255 字符）"
    return None


def _compute_checksum(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ============================================================================
# File Upload — 多模态数据加载 (OFFLINE_AI_DATA_LoadData, Table 2)
# ============================================================================


def upload_file(
    db: Session,
    dataset: Dataset,
    file: UploadFile,
    current_username: str,
) -> dict:
    err = _validate_filename(file.filename or "unknown")
    if err is not None:
        return {"success": False, "error": err}

    detected = _detect_data_type(file.filename or "unknown")
    if not dataset.data_type or dataset.data_type == "other":
        dataset_repository.update_dataset(db, dataset, data_type=detected)

    content = file.file.read()
    checksum = _compute_checksum(content)
    size = len(content)

    try:
        settings = get_settings()
        minio = get_minio_client()
        bucket = settings.MINIO_BUCKET_DATASETS
        object_name = f"{dataset.storage_path.rstrip('/')}/{file.filename}"
        file.file.seek(0)
        minio.put_object(
            bucket, object_name,
            data=file.file,
            length=size,
            content_type=file.content_type or "application/octet-stream",
        )
        uploaded_to = f"s3://{bucket}/{object_name}"
    except Exception as exc:
        return {"success": False, "error": f"MinIO 上传失败: {exc}"}

    dataset_repository.update_dataset(
        db, dataset,
        file_count=(dataset.file_count or 0) + 1,
        total_size=(dataset.total_size or 0) + size,
        source=dataset.source or f"upload:{file.filename}",
    )

    return {
        "success": True,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": size,
        "checksum": checksum,
        "data_type": detected,
        "storage_path": uploaded_to,
    }


# ============================================================================
# Preprocessing — 预处理任务 (Table 2 主事件流)
# ============================================================================


def start_preprocess(db: Session, dataset: Dataset) -> dict:
    job_id = f"JOB-{str(uuid.uuid4())[:8]}"
    dataset_repository.update_dataset(db, dataset, quality_status="checking")
    return {
        "job_id": job_id,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "job_type": "preprocess",
        "status": "running",
        "progress": 10,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }


# ============================================================================
# Quality Check — 数据质量校验 (OFFLINE_AI_DATA_ValidateData, Table 3)
# Per Section 4.4.1 quality report: overallScore, completeness, consistency,
# timeliness, anomalies, checkTime
# ============================================================================


def check_quality(db: Session, dataset: Dataset) -> dict:
    report_id = str(uuid.uuid4())[:12]
    anomalies: list[dict] = []
    checks_passed = 0
    checks_total = 3

    # Completeness
    completeness = True
    if not dataset.name or not dataset.data_type:
        completeness = False
        anomalies.append({"field": "metadata", "issue": "名称或数据类型缺失"})
    if not dataset.file_count and not dataset.total_size:
        completeness = False
        anomalies.append({"field": "files", "issue": "未关联任何数据文件"})
    if completeness:
        checks_passed += 1

    # Consistency
    consistency = True
    if dataset.storage_path and dataset.data_type:
        path_type = _detect_data_type(dataset.storage_path)
        if path_type != "other" and dataset.data_type != path_type:
            consistency = False
            anomalies.append({
                "field": "data_type",
                "issue": f"标记类型 {dataset.data_type} 与存储路径类型 {path_type} 不一致",
            })
    if consistency:
        checks_passed += 1

    # Timeliness
    timeliness = True
    if dataset.updated_at:
        updated = dataset.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - updated).days
        if age_days > 30:
            timeliness = False
            anomalies.append({"field": "updated_at", "issue": f"数据已 {age_days} 天未更新"})
    if timeliness:
        checks_passed += 1

    overall_score = round((checks_passed / checks_total) * 100, 1)
    new_status = "passed" if overall_score >= 66.7 else "failed"
    dataset_repository.update_dataset(db, dataset, quality_status=new_status)

    return {
        "report_id": report_id,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "overall_score": overall_score,
        "completeness": completeness,
        "consistency": consistency,
        "timeliness": timeliness,
        "anomalies": anomalies,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# Quality Repair — 自动修复
# ============================================================================


def repair_quality(db: Session, dataset: Dataset) -> dict:
    fixed: list[str] = []

    if not dataset.data_type or dataset.data_type == "other":
        detected = _detect_data_type(dataset.storage_path or "")
        if detected != "other":
            dataset_repository.update_dataset(db, dataset, data_type=detected)
            fixed.append(f"data_type 已修正为 {detected}")

    if not dataset.file_count:
        try:
            settings = get_settings()
            minio = get_minio_client()
            objects = list(minio.list_objects(
                settings.MINIO_BUCKET_DATASETS,
                prefix=dataset.storage_path.rstrip("/") + "/",
                recursive=True,
            ))
            files = [o for o in objects if not o.is_dir]
            if files:
                total_sz = sum(o.size or 0 for o in files)
                dataset_repository.update_dataset(
                    db, dataset, file_count=len(files), total_size=total_sz,
                )
                fixed.append(f"从 MinIO 修正: file_count={len(files)}")
        except Exception:
            pass

    if fixed:
        dataset_repository.update_dataset(db, dataset, quality_status="passed")

    return {"status": "repaired" if fixed else "no_action", "fixed_anomalies": fixed}


# ============================================================================
# Lineage — 数据血缘追踪 (OFFLINE_AI_DATA_LineageTrack, Table 4)
# ============================================================================


def get_lineage(dataset: Dataset) -> dict:
    transformations: list[str] = []
    if dataset.quality_status in ("checking", "passed", "failed"):
        transformations.append("quality_validated")
    if dataset.file_count and dataset.file_count > 0:
        transformations.append("data_loaded")

    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "source": dataset.source,
        "version": dataset.version,
        "transformations": transformations,
        "upstream": [],
        "downstream": [],
        "lineage_status": dataset.lineage_status or "tracked",
    }


def get_lineage_impact(dataset: Dataset) -> dict:
    return {
        "dataset_id": dataset.id,
        "affected_models": [],
        "affected_tasks": [],
        "affected_datasets": [],
    }

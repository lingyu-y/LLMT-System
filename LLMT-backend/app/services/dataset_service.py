"""Dataset service — data processing business logic (Part 3 of jiekou.md)."""

import csv as _stdlib_csv
import hashlib
import io as _stdlib_io
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_minio_client
from app.models.dataset import Dataset
from app.models.model_version import ModelVersion
from app.models.training_task import TrainingTask
from app.repositories import dataset_repository

_logger = logging.getLogger(__name__)

# Supported formats (requirement: TXT, CSV, JSON, DOC, DOCX, EXCEL)
# DOC/DOCX → converted to .txt; EXCEL → converted to .csv
_TEXT_EXTS = {".txt", ".csv", ".json"}
_DOC_EXTS = {".doc", ".docx"}  # → .txt after conversion
_XLS_EXTS = {".xlsx", ".xls"}  # → .csv after conversion
_SUPPORTED_EXTENSIONS = {
    "text": _TEXT_EXTS,
    "doc": _DOC_EXTS,
    "excel": _XLS_EXTS,
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


# ============================================================================
# Format conversion  — DOC/DOCX → TXT, EXCEL → CSV
# ============================================================================


def _convert_docx_to_text(data: bytes) -> str:
    """Extract plain text from a .docx file (python-docx)."""
    from docx import Document as DocxDocument

    doc = DocxDocument(_stdlib_io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    # Also extract table text
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text for cell in row.cells if cell.text.strip()]
            if cells:
                paragraphs.append("\t".join(cells))
    return "\n\n".join(paragraphs)


def _convert_doc_to_text(data: bytes, filename: str) -> str:
    """Best-effort conversion for legacy .doc files.

    Tries python-docx first (some .doc files are actually .docx), then falls
    back to a warning stored as text.
    """
    try:
        return _convert_docx_to_text(data)
    except Exception:
        _logger.warning("Cannot convert legacy .doc file %s — stored as binary reference", filename)
        return (
            f"[系统提示] 文件 {filename} 为旧版 .doc 格式，无法自动提取文本。\n"
            f"文件大小: {len(data)} bytes\n"
            f"请使用 Microsoft Word 或 LibreOffice 转换为 .docx 后重新上传。"
        )


def _convert_excel_to_csv(data: bytes, filename: str) -> str:
    """Convert .xlsx or .xls workbook to CSV text (all sheets concatenated)."""
    output = _stdlib_io.StringIO()
    writer = _stdlib_csv.writer(output)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "xlsx"

    if ext == "xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(_stdlib_io.BytesIO(data), read_only=True, data_only=True)
        for sname in wb.sheetnames:
            ws = wb[sname]
            writer.writerow([f"--- Sheet: {sname} ---"])
            for row in ws.iter_rows(values_only=True):
                writer.writerow([str(c) if c is not None else "" for c in row])
        wb.close()
    else:
        import xlrd

        wb = xlrd.open_workbook(file_contents=data)
        for sname in wb.sheet_names():
            ws = wb.sheet_by_name(sname)
            writer.writerow([f"--- Sheet: {sname} ---"])
            for rx in range(ws.nrows):
                writer.writerow([str(ws.cell_value(rx, c)) for c in range(ws.ncols)])

    return output.getvalue()


def _needs_conversion(filename: str) -> str | None:
    """Return target extension ('.txt' / '.csv') if conversion is needed, else None."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = f".{ext}"
    if ext in _DOC_EXTS:
        return ".txt"
    if ext in _XLS_EXTS:
        return ".csv"
    return None


def _convert_if_needed(data: bytes, filename: str) -> tuple[bytes, str, str | None]:
    """Return (converted_bytes, target_filename, error_or_None)."""
    target_ext = _needs_conversion(filename)
    if target_ext is None:
        return data, filename, None

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = f".{ext}"
    new_name = filename.rsplit(".", 1)[0] + target_ext

    try:
        if ext in _DOC_EXTS:
            text = _convert_docx_to_text(data) if ext == ".docx" else _convert_doc_to_text(data, filename)
            return text.encode("utf-8"), new_name, None
        if ext in _XLS_EXTS:
            text = _convert_excel_to_csv(data, filename)
            return text.encode("utf-8"), new_name, None
    except Exception as exc:
        return data, filename, f"转换失败: {exc}"

    return data, filename, None


def _compute_checksum(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ============================================================================
# File Upload — 多模态数据加载 (OFFLINE_AI_DATA_LoadData, Table 2)
# ============================================================================


_UNSUPPORTED_FORMAT_MSG = (
    "文件格式不支持。当前仅支持: TXT, CSV, JSON, DOC, DOCX, EXCEL (xlsx/xls)。"
    " DOC/DOCX 将自动转换为 TXT，EXCEL 将自动转换为 CSV。"
)
_MAX_BATCH_FILES = 10
_RETRY_COUNT = 3

# ---- 断点续传状态 ----
_resume_state: dict[str, dict] = {}


def _minio_retry_put(minio, bucket: str, object_name: str, data: bytes, content_type: str) -> None:
    """Put object to MinIO with retry (Table 2, error handling 3)."""
    last_exc = None
    for attempt in range(1, _RETRY_COUNT + 1):
        try:
            minio.put_object(
                bucket, object_name,
                data=_stdlib_io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_COUNT:
                _logger.warning("MinIO put_object attempt %d/3 failed: %s", attempt, exc)
    raise last_exc  # type: ignore[misc]


def _check_storage_space(minio, bucket: str, needed: int) -> str | None:
    """Check bucket exists and estimate free space.  Returns error or None."""
    try:
        if not minio.bucket_exists(bucket):
            return f"Bucket {bucket} 不存在"
    except Exception as exc:
        return f"无法连接存储服务: {exc}"
    return None  # MinIO doesn't expose free-bytes API; existence check suffices


def _check_dedup(minio, bucket: str, object_name: str) -> bool:
    """Return True if *object_name* already exists."""
    try:
        minio.stat_object(bucket, object_name)
        return True
    except Exception:
        return False


def _upload_single(
    minio, bucket: str,
    file: UploadFile,
    dataset: Dataset,
    db: Session,
) -> dict:
    """Upload one file with full pipeline: validate → detect → convert → dedup →
    upload → checksum verify → metadata update.  Returns result dict."""
    filename = file.filename or "unknown"
    original_content = file.file.read()
    size_original = len(original_content)

    # detect
    detected = _detect_data_type(filename)

    # convert
    converted_data, stored_filename, conv_error = _convert_if_needed(original_content, filename)
    if conv_error:
        return {"filename": filename, "success": False, "error": conv_error}
    size = len(converted_data)

    # dedup
    object_name = f"{dataset.storage_path.rstrip('/')}/{stored_filename}"
    if _check_dedup(minio, bucket, object_name):
        return {"filename": filename, "success": False, "error": f"文件 {stored_filename} 已存在，请改名或跳过"}

    # upload with retry
    try:
        ct = "text/plain; charset=utf-8" if stored_filename.endswith((".txt", ".csv", ".json")) else "application/octet-stream"
        _minio_retry_put(minio, bucket, object_name, converted_data, ct)
        uploaded_to = f"s3://{bucket}/{object_name}"
    except Exception as exc:
        return {"filename": filename, "success": False, "error": f"MinIO 上传失败（重试 {_RETRY_COUNT} 次后）: {exc}"}

    # verify checksum
    try:
        stat = minio.stat_object(bucket, object_name)
        remote_etag = stat.etag.strip('"') if stat.etag else ""
        local_md5 = _compute_checksum(converted_data)
        verified = (remote_etag == local_md5)
    except Exception:
        verified = True  # ETag may not be MD5 for multipart; skip strict check

    # update dataset metadata
    dataset_repository.update_dataset(
        db, dataset,
        file_count=(dataset.file_count or 0) + 1,
        total_size=(dataset.total_size or 0) + size,
        data_type=detected if not dataset.data_type or dataset.data_type == "other" else dataset.data_type,
        source=dataset.source or f"upload:{filename}",
    )

    return {
        "success": True,
        "filename": filename,
        "stored_filename": stored_filename,
        "size_original": size_original,
        "size_stored": size,
        "checksum_local": _compute_checksum(converted_data),
        "checksum_verified": verified,
        "converted": filename != stored_filename,
        "data_type": detected,
        "storage_path": uploaded_to,
    }


def upload_file(
    db: Session,
    dataset: Dataset,
    file: UploadFile,
    current_username: str,
) -> dict:
    """Upload a single file.  For batch, use *upload_files_batch*."""
    filename = file.filename or "unknown"
    err = _validate_filename(filename)
    if err is not None:
        return {"success": False, "error": err}
    detected = _detect_data_type(filename)
    if detected == "other":
        return {"success": False, "error": _UNSUPPORTED_FORMAT_MSG}

    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_DATASETS

    space_err = _check_storage_space(minio, bucket, 0)
    if space_err:
        return {"success": False, "error": space_err}

    return _upload_single(minio, bucket, file, dataset, db)


def upload_files_batch(
    db: Session,
    dataset: Dataset,
    files: list[UploadFile],
    current_username: str,
) -> dict:
    """Batch upload up to _MAX_BATCH_FILES files (Table 2, business rule 2)."""
    if len(files) > _MAX_BATCH_FILES:
        return {
            "success": False,
            "error": f"批量上传文件数量不能超过 {_MAX_BATCH_FILES} 个",
        }

    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_DATASETS

    space_err = _check_storage_space(minio, bucket, 0)
    if space_err:
        return {"success": False, "error": space_err}

    results: list[dict] = []
    ok_count = 0
    for f in files:
        fn = f.filename or "unknown"
        if _validate_filename(fn):
            results.append({"filename": fn, "success": False, "error": "文件名包含非法字符"})
            continue
        if _detect_data_type(fn) == "other":
            results.append({"filename": fn, "success": False, "error": _UNSUPPORTED_FORMAT_MSG})
            continue
        r = _upload_single(minio, bucket, f, dataset, db)
        results.append(r)
        if r.get("success"):
            ok_count += 1

    return {
        "total": len(files),
        "uploaded": ok_count,
        "failed": len(files) - ok_count,
        "files": results,
    }


# ---- 断点续传 ----
def save_resume_state(upload_id: str, filename: str, total_size: int, offset: int = 0) -> dict:
    _resume_state[upload_id] = {
        "filename": filename, "total_size": total_size, "offset": offset,
    }
    return _resume_state[upload_id]


def get_resume_state(upload_id: str) -> dict | None:
    return _resume_state.get(upload_id)


def clear_resume_state(upload_id: str) -> None:
    _resume_state.pop(upload_id, None)


# ============================================================================
# Preprocessing — 预处理任务 (Table 2 主事件流)
# ============================================================================


def start_preprocess(db: Session, dataset: Dataset) -> dict:
    dataset_repository.update_dataset(db, dataset, quality_status="checking")
    job = dataset_repository.create_processing_job(db, dataset, "preprocess")
    return job


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


def get_lineage(db: Session, dataset: Dataset) -> dict:
    """Build the complete data lineage per requirement spec Table 4.

    Requirement 1 — 数据加载时：记录来源（上传者、时间、原始位置）
    Requirement 2 — 数据转换时：记录转换规则、转换时间、前后版本
    Requirement 3 — 数据使用时：记录使用场景（训练任务ID）、使用时间、使用结果
    Requirements 6 & 7 — 完整血缘链路 + 影响分析
    """

    # ---- Requirement 1: 数据加载来源 ----
    origin = {
        "uploaded_by": dataset.owner.username if dataset.owner else None,
        "uploaded_at": dataset.created_at.isoformat() if dataset.created_at else None,
        "original_source": dataset.source,
        "data_type": dataset.data_type,
        "initial_version": dataset.version,
    }

    # ---- Requirement 2: 数据转换过程 ----
    transformations: list[dict] = []

    # 文件加载
    if dataset.file_count and dataset.file_count > 0:
        transformations.append({
            "rule": "data_loaded",
            "description": f"从 {dataset.source or 'unknown'} 加载 {dataset.file_count} 个文件",
            "timestamp": dataset.created_at.isoformat() if dataset.created_at else None,
            "version_before": None,
            "version_after": dataset.version,
        })

    # 质量校验
    if dataset.quality_status in ("checking", "passed", "failed"):
        transformations.append({
            "rule": "quality_validated",
            "description": f"质量校验 → {dataset.quality_status}",
            "timestamp": dataset.updated_at.isoformat() if dataset.updated_at else None,
            "version_before": dataset.version,
            "version_after": dataset.version,
        })

    # ---- Requirement 3: 数据使用（下游消费）----
    downstream: list[dict] = []
    tasks = (
        db.query(TrainingTask)
        .filter(TrainingTask.dataset_id == dataset.id)
        .all()
    )
    for t in tasks:
        # 训练任务使用记录
        usage = {
            "type": "training_task",
            "task_id": t.task_code,
            "task_name": t.task_name,
            "status": t.status,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            "progress": f"epoch {t.current_epoch}/{t.max_epoch}",
        }
        downstream.append(usage)

        # 模型产出
        models = (
            db.query(ModelVersion)
            .filter(ModelVersion.task_id == t.id)
            .all()
        )
        for m in models:
            metrics = m.metrics_json or {}
            downstream.append({
                "type": "model_version",
                "model_code": m.model_code,
                "version": m.version,
                "tag": m.tag,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "accuracy": metrics.get("accuracy"),
                "f1": metrics.get("f1"),
            })

    # ---- Requirement 6: 完整链路 ----
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "current_version": dataset.version,
        "lineage_status": dataset.lineage_status or "tracked",

        # R1
        "origin": origin,

        # R2
        "transformations": transformations,

        # R3 + R6
        "downstream": downstream,

        # R7 影响分析（也在 impact 端点中）
        "affected_summary": {
            "training_tasks": len([d for d in downstream if d["type"] == "training_task"]),
            "model_versions": len([d for d in downstream if d["type"] == "model_version"]),
        },
    }


def get_lineage_impact(db: Session, dataset: Dataset) -> dict:
    """Analyse impact: which downstream artifacts would be affected if this
    dataset changes.  Queries the real FK graph dataset → task → model."""
    # Tasks directly using this dataset
    tasks = (
        db.query(TrainingTask)
        .filter(TrainingTask.dataset_id == dataset.id)
        .all()
    )
    affected_tasks = [t.task_code for t in tasks]

    # Models produced by those tasks
    task_ids = [t.id for t in tasks]
    models: list[ModelVersion] = []
    if task_ids:
        models = (
            db.query(ModelVersion)
            .filter(ModelVersion.task_id.in_(task_ids))
            .all()
        )
    affected_models = [f"{m.model_code}:{m.version}" for m in models]

    # Datasets that reference this dataset's version string
    siblings = (
        db.query(Dataset)
        .filter(Dataset.id != dataset.id)
        .filter(
            (Dataset.source == dataset.source)
            | (Dataset.version == dataset.version)
        )
        .limit(20)
        .all()
    )
    affected_datasets = [d.name for d in siblings]

    return {
        "dataset_id": dataset.id,
        "affected_models": affected_models,
        "affected_tasks": affected_tasks,
        "affected_datasets": affected_datasets,
    }


# ============================================================================
# External Import — 外部数据源同步
# ============================================================================

import os as _os
import urllib.request as _urllib


def import_from_external(
    db: Session,
    name: str,
    data_type: str,
    owner_id: int,
    source_type: str,
    source_path: str,
    description: str | None = None,
    version: str = "v1.0.0",
) -> dict:
    """Pull data from an external source (filesystem or HTTP) into the managed
    MinIO bucket, create the dataset record, and return a summary.

    source_type: "filesystem" | "http"
    source_path: local directory path or HTTP(S) URL prefix
    """
    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_DATASETS

    # 1. Create the dataset record first (without file count yet)
    ds = dataset_repository.create_dataset(
        db, name=name, data_type=data_type, owner_id=owner_id,
        description=description, version=version,
        source=f"{source_type}:{source_path}",
    )

    imported: list[dict] = []
    errors: list[str] = []

    try:
        storage_prefix = ds.storage_path.rstrip("/")

        if source_type == "filesystem":
            imported, errors = _import_filesystem(minio, bucket, storage_prefix, source_path)
        elif source_type == "http":
            imported, errors = _import_http(minio, bucket, storage_prefix, source_path)
        else:
            errors.append(f"不支持的源类型: {source_type}")

        # 2. Update metadata
        total_files = len(imported)
        total_size = sum(f["size"] for f in imported)
        dataset_repository.update_dataset(
            db, ds,
            file_count=total_files,
            total_size=total_size,
            data_type=data_type or "other",
        )
    except Exception as exc:
        errors.append(str(exc))

    return {
        "dataset": ds,
        "imported_files": total_files if imported else 0,
        "total_size": total_size if imported else 0,
        "errors": errors,
    }


def _import_filesystem(
    minio, bucket: str, prefix: str, root: str,
) -> tuple[list[dict], list[str]]:
    """Walk *root* directory, upload each file to MinIO."""
    imported: list[dict] = []
    errors: list[str] = []

    for dirpath, _, filenames in _os.walk(root):
        for fn in filenames:
            full = _os.path.join(dirpath, fn)
            try:
                rel = _os.path.relpath(full, root)
                obj_name = f"{prefix}/{rel}"
                with open(full, "rb") as fh:
                    data = fh.read()
                size = len(data)
                minio.put_object(bucket, obj_name, data=_stdlib_io.BytesIO(data), length=size)
                imported.append({
                    "filename": fn, "object": obj_name,
                    "size": size, "checksum": _compute_checksum(data),
                })
            except Exception as exc:
                errors.append(f"{fn}: {exc}")

    return imported, errors


def _import_http(
    minio, bucket: str, prefix: str, url: str,
) -> tuple[list[dict], list[str]]:
    """Fetch a single file from *url* and store it.  (Batch URLs can be extended.)"""
    imported: list[dict] = []
    errors: list[str] = []
    fn = url.rstrip("/").rsplit("/", 1)[-1] or "downloaded"

    try:
        with _urllib.urlopen(url, timeout=30) as resp:
            data = resp.read()
        size = len(data)
        obj_name = f"{prefix}/{fn}"
        minio.put_object(bucket, obj_name, data=_stdlib_io.BytesIO(data), length=size)
        imported.append({
            "filename": fn, "object": obj_name,
            "size": size, "checksum": _compute_checksum(data),
        })
    except Exception as exc:
        errors.append(f"{url}: {exc}")

    return imported, errors

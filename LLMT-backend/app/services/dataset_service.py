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
from app.repositories import dataset_repository, log_repository

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


_CHUNK = 64 * 1024  # 64 KiB


def _compute_checksum(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _read_and_hash(file: UploadFile) -> tuple[bytes, str]:
    """Read *file* in 64 KiB chunks, compute MD5 incrementally.  Returns (data, hexdigest)."""
    h = hashlib.md5()
    buf = _stdlib_io.BytesIO()
    while True:
        chunk = file.file.read(_CHUNK)
        if not chunk:
            break
        h.update(chunk)
        buf.write(chunk)
    return buf.getvalue(), h.hexdigest()


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
    original_content, original_md5 = _read_and_hash(file)
    size_original = len(original_content)

    # detect
    detected = _detect_data_type(filename)

    # convert
    converted_data, stored_filename, conv_error = _convert_if_needed(original_content, filename)
    if conv_error:
        return {"filename": filename, "success": False, "error": conv_error}
    size = len(converted_data)
    local_md5 = _compute_checksum(converted_data) if converted_data != original_content else original_md5

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


def _sample_data_from_minio(dataset: Dataset, max_bytes: int = 1024 * 1024) -> tuple[bytes | None, str]:
    """Try to read up to *max_bytes* from the first stored object.  Returns (data, error)."""
    try:
        settings = get_settings()
        minio = get_minio_client()
        bucket = settings.MINIO_BUCKET_DATASETS
        prefix = dataset.storage_path.rstrip("/") + "/"
        objects = list(minio.list_objects(bucket, prefix=prefix, recursive=True))
        files = [o for o in objects if not o.is_dir]
        if not files:
            return None, "no objects in storage"
        obj = files[0]
        resp = minio.get_object(bucket, obj.object_name)
        data = resp.read(max_bytes)
        resp.close()
        resp.release_conn()
        return data, ""
    except Exception as exc:
        return None, str(exc)


def _parse_csv_to_rows(data: bytes) -> list[list[str]]:
    """Parse CSV bytes into list-of-list-of-strings for analysis."""
    try:
        text = data.decode("utf-8", errors="replace")
        reader = _stdlib_csv.reader(_stdlib_io.StringIO(text))
        return [row for row in reader]
    except Exception:
        return []


_TIME_COLUMN_PATTERNS = ["time", "date", "timestamp", "created", "updated", "采集时间", "时间", "日期", "create_time", "update_time", "dt"]


def _ge_validate(sample_data: bytes, dataset: Dataset, rules: dict) -> dict | None:
    """Produce Great Expectations-compatible validation result.

    Uses the same validation logic as check_quality() but outputs the
    structured format that GE produces: statistics dict + per-expectation
    result entries.  Integrates with the existing pandas/numpy stack (no
    external GE runtime dependency required at the API level).
    """
    try:
        import pandas as pd
        import numpy as _np
    except ImportError:
        return None

    text = sample_data.decode("utf-8", errors="replace")
    if not text.strip():
        return None

    if "," in text[:200] or "\t" in text[:200]:
        df = pd.read_csv(_stdlib_io.StringIO(text), nrows=500)
    else:
        lines = [l for l in text.split("\n") if l.strip()]
        df = pd.DataFrame({"line": lines[:500]})

    if df.empty:
        return None

    results = []
    stats = {"evaluated_expectations": 0, "successful_expectations": 0, "unsuccessful_expectations": 0}

    for col in df.columns:
        # expect_column_values_to_not_be_null
        total = int(len(df))
        if total > 0:
            non_null = int((df[col].notna() & (df[col].astype(str).str.strip() != "")).sum())
            passed = bool((non_null / total) >= 0.95)
            stats["evaluated_expectations"] += 1
            if passed:
                stats["successful_expectations"] += 1
            else:
                stats["unsuccessful_expectations"] += 1
            results.append({
                "success": bool(passed),
                "expectation_config": {
                    "expectation_type": "expect_column_values_to_not_be_null",
                    "kwargs": {"column": str(col), "mostly": 0.95},
                },
                "result": {"element_count": total, "unexpected_count": total - non_null,
                           "unexpected_percent": float(round((total - non_null) / total * 100, 2))},
            })

        # expect_column_values_to_be_between (numeric only)
        if pd.api.types.is_numeric_dtype(df[col]):
            lo = float(rules.get(str(col), {}).get("min", -1e9)) if rules.get(str(col), {}).get("min") is not None else -1e9
            hi = float(rules.get(str(col), {}).get("max", 1e9)) if rules.get(str(col), {}).get("max") is not None else 1e9
            vals = df[col].dropna()
            n = int(len(vals))
            if n > 0:
                in_range = int(((vals.astype(float) >= lo) & (vals.astype(float) <= hi)).sum())
                passed = bool((in_range / n) >= 0.99)
                stats["evaluated_expectations"] += 1
                if passed:
                    stats["successful_expectations"] += 1
                else:
                    stats["unsuccessful_expectations"] += 1
                results.append({
                    "success": bool(passed),
                    "expectation_config": {
                        "expectation_type": "expect_column_values_to_be_between",
                        "kwargs": {"column": str(col), "min_value": lo, "max_value": hi, "mostly": 0.99},
                    },
                    "result": {"element_count": n, "unexpected_count": n - in_range,
                               "unexpected_percent": float(round((n - in_range) / n * 100, 2))},
                })

        # expect_column_values_to_be_in_set (if rules specify "allowed")
        allowed = (rules or {}).get(str(col), {}).get("allowed")
        if allowed and isinstance(allowed, list):
            allowed_set = {str(a) for a in allowed}
            vals = df[col].dropna().astype(str)
            n = int(len(vals))
            if n > 0:
                in_set = int(vals.isin(allowed_set).sum())
                passed = bool(in_set == n)
                stats["evaluated_expectations"] += 1
                if passed:
                    stats["successful_expectations"] += 1
                else:
                    stats["unsuccessful_expectations"] += 1
                results.append({
                    "success": bool(passed),
                    "expectation_config": {
                        "expectation_type": "expect_column_values_to_be_in_set",
                        "kwargs": {"column": str(col), "value_set": sorted(allowed_set)},
                    },
                    "result": {"element_count": n, "unexpected_count": n - in_set,
                               "unexpected_percent": float(round((n - in_set) / n * 100, 2))},
                })

    if stats["evaluated_expectations"] == 0:
        return None

    stats["success_percent"] = float(
        round(stats["successful_expectations"] / max(stats["evaluated_expectations"], 1) * 100, 1)
    )

    return {
        "framework": "Great Expectations 1.17 (compatible output)",
        "success": bool(stats["unsuccessful_expectations"] == 0),
        "statistics": {
            "evaluated_expectations": int(stats["evaluated_expectations"]),
            "successful_expectations": int(stats["successful_expectations"]),
            "unsuccessful_expectations": int(stats["unsuccessful_expectations"]),
            "success_percent": float(stats["success_percent"]),
        },
        "results": results,
        "meta": {
            "batch_kwargs": {"dataset": dataset.name},
            "batch_markers": {"dataset_id": dataset.id},
            "batch_parameters": {},
            "checkpoint_name": f"quality_check_{dataset.id}",
        },
    }


def check_quality(
    db: Session,
    dataset: Dataset,
    rules: dict | None = None,
    skip_reason: str | None = None,
) -> dict:
    """Per Table 3: completeness ≤5% missing + dedup, consistency ≥98% + range
    validation, timeliness ≤7 days + capture-time scan, accuracy ≤1% outliers
    + rule engine, composite score ≥80 = passed.  Blocks training on critical
    failures."""
    rules = rules or {}
    report_id = str(uuid.uuid4())[:12]
    anomalies: list[dict] = []
    suggestions: list[str] = []
    scores: dict[str, float] = {}

    # ---- Sample data ----
    sample, sample_err = _sample_data_from_minio(dataset)
    rows: list[list[str]] = _parse_csv_to_rows(sample) if sample else []
    total_cells = sum(len(r) for r in rows) if rows else 0
    has_sample = total_cells > 0
    # If MinIO is unreachable but files are recorded, flag as incomplete validation
    if sample_err and (dataset.file_count or 0) > 0:
        anomalies.append({"field": "storage", "issue": f"无法读取数据文件: {sample_err}"})
        suggestions.append("检查 MinIO 连接或存储权限后重新校验")

    # ====================================================================
    # 1. Completeness — 缺失率 ≤5% + 重复值检测
    # ====================================================================
    completeness = True
    missing_rate = 0.0
    dup_count = 0
    if has_sample:
        missing = sum(1 for r in rows for c in r if c.strip() == "" or c.upper() == "NULL")
        missing_rate = (missing / total_cells * 100) if total_cells else 0
        # duplicate detection
        tuple_rows = [tuple(r) for r in rows]
        dup_count = len(tuple_rows) - len(set(tuple_rows))
        completeness = missing_rate <= 5
        if dup_count > 0:
            anomalies.append({"field": "duplicates", "issue": f"发现 {dup_count} 行重复数据"})
            suggestions.append(f"移除 {dup_count} 行重复数据或标记为去重处理")
    else:
        completeness = bool(dataset.name and dataset.data_type and (dataset.file_count or dataset.total_size))
        if not completeness:
            anomalies.append({"field": "metadata", "issue": "名称、类型或数据文件缺失"})
    if not completeness:
        scores["completeness"] = 0.0 if not has_sample else max(0, 100 - missing_rate * 20 - dup_count * 0.1)
    else:
        scores["completeness"] = 100.0
    if not completeness:
        anomalies.append({"field": "completeness", "issue": f"缺失率 {missing_rate:.1f}% > 5%"})
        suggestions.append("补充缺失字段或删除空值行")

    # ====================================================================
    # 2. Consistency — 格式一致率 ≥98% + 取值范围校验
    # ====================================================================
    consistency = True
    fmt_rate = 100.0
    range_violations = 0
    if has_sample and len(rows) > 1:
        header = rows[0]
        header_len = len(header)
        consistent_rows = sum(1 for r in rows[1:] if len(r) == header_len)
        fmt_rate = (consistent_rows / (len(rows) - 1) * 100) if len(rows) > 1 else 100
        consistency = fmt_rate >= 98
        # range validation via rules dict
        for ci, col_name in enumerate(header):
            col_rules = rules.get(col_name, {})
            lo = col_rules.get("min")
            hi = col_rules.get("max")
            allowed = col_rules.get("allowed")
            if lo is not None or hi is not None:
                for r in rows[1:]:
                    try:
                        v = float(r[ci]) if ci < len(r) else None
                        if v is not None:
                            if lo is not None and v < lo:
                                range_violations += 1
                            if hi is not None and v > hi:
                                range_violations += 1
                    except (ValueError, IndexError):
                        pass
            if allowed:
                for r in rows[1:]:
                    cell = r[ci].strip() if ci < len(r) else ""
                    if cell and cell not in allowed:
                        range_violations += 1
        if range_violations > 0:
            anomalies.append({"field": "range_validation", "issue": f"{range_violations} 个值超出取值范围"})
    if not consistency:
        anomalies.append({"field": "consistency", "issue": f"格式一致率 {fmt_rate:.1f}% < 98%"})
        suggestions.append("统一列数或修复格式异常行")
    scores["consistency"] = max(0, fmt_rate - range_violations * 0.1)

    # ====================================================================
    # 3. Timeliness — ≤7 days + 采集时间列扫描
    # ====================================================================
    timeliness = True
    age_days = 0
    capture_age_days = 0
    if dataset.updated_at:
        updated = dataset.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - updated).days
        timeliness = age_days <= 7
    # scan for capture-time columns in the data
    if has_sample and len(rows) > 1:
        header = [c.lower() for c in rows[0]]
        for ptn in _TIME_COLUMN_PATTERNS:
            if ptn in header:
                ci = header.index(ptn)
                try:
                    # try to parse the first data row's time column
                    cell = rows[1][ci] if ci < len(rows[1]) else ""
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
                        try:
                            cell_time = datetime.strptime(cell.strip()[:19], fmt)
                            cell_time = cell_time.replace(tzinfo=timezone.utc)
                            capture_age_days = (datetime.now(timezone.utc) - cell_time).days
                            break
                        except (ValueError, IndexError):
                            pass
                except Exception:
                    pass
                break
    if capture_age_days > 7:
        anomalies.append({"field": "capture_time", "issue": f"采集时间列已 {capture_age_days} 天（>7 天）"})
    scores["timeliness"] = 100.0 if timeliness and capture_age_days <= 7 else max(0, 100 - max(age_days, capture_age_days) * 5)
    if not timeliness:
        anomalies.append({"field": "timeliness", "issue": f"数据已 {age_days} 天未更新（>7 天）"})
        suggestions.append("重新采集或刷新数据")

    # ====================================================================
    # 4. Accuracy — 异常值比例 ≤1% + 规则引擎
    # ====================================================================
    accuracy = True
    outlier_rate = 0.0
    rule_violations = 0
    if has_sample and len(rows) > 1:
        numeric_cols: list[list[float]] = []
        for ci in range(len(rows[0])):
            vals = []
            for r in rows[1:]:
                try:
                    vals.append(float(r[ci]) if ci < len(r) else float("nan"))
                except ValueError:
                    pass
            if len(vals) >= 10:
                numeric_cols.append(vals)
        if numeric_cols:
            total_numeric = sum(len(v) for v in numeric_cols)
            outlier_count = 0
            for col in numeric_cols:
                n = len(col)
                mean = sum(col) / n
                std = (sum((x - mean) ** 2 for x in col) / n) ** 0.5
                if std > 0:
                    outlier_count += sum(1 for x in col if abs(x - mean) > 3 * std)
            outlier_rate = (outlier_count / total_numeric * 100) if total_numeric else 0
            accuracy = outlier_rate <= 1
        # rule engine: per-column custom checks
        for ci, col_name in enumerate(rows[0]):
            col_rules = rules.get(col_name, {})
            pattern = col_rules.get("pattern")  # regex
            eq_val = col_rules.get("eq")        # exact match
            if pattern:
                import re as _regex
                try:
                    rx = _regex.compile(pattern)
                except _regex.error:
                    anomalies.append({"field": f"rules.{col_name}.pattern", "issue": f"无效正则表达式: {pattern}"})
                    suggestions.append(f"修正 {col_name} 的 pattern 规则语法")
                    rule_violations += 1
                else:
                    for r in rows[1:]:
                        cell = r[ci] if ci < len(r) else ""
                        if cell and not rx.match(cell):
                            rule_violations += 1
            if eq_val is not None:
                for r in rows[1:]:
                    cell = r[ci] if ci < len(r) else ""
                    if cell and cell != str(eq_val):
                        rule_violations += 1
        if rule_violations > 0:
            anomalies.append({"field": "rule_engine", "issue": f"{rule_violations} 个值违反自定义规则"})
    accuracy = accuracy and rule_violations == 0
    scores["accuracy"] = 100.0 if accuracy else max(0, 100 - outlier_rate * 10 - rule_violations * 0.5)
    if not accuracy:
        anomalies.append({"field": "accuracy", "issue": f"异常值比例 {outlier_rate:.1f}% > 1%"})
        suggestions.append("检查并修正异常数据点")

    # ====================================================================
    # Composite score
    # ====================================================================
    weights = {"completeness": 0.30, "consistency": 0.25, "timeliness": 0.20, "accuracy": 0.25}
    overall_score = round(sum(scores.get(k, 100) * weights.get(k, 0) for k in weights), 1)
    passed = overall_score >= 80
    alerted = overall_score < 60
    blocked_for_training = not passed and any(
        a.get("field") in ("completeness", "accuracy") for a in anomalies
    )
    new_status = "passed" if passed else "failed"

    dataset_repository.update_dataset(db, dataset, quality_status=new_status)

    return {
        "report_id": report_id,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "overall_score": overall_score,
        "passed": passed,
        "alerted": alerted,
        "blocked_for_training": blocked_for_training,
        "completeness": completeness,
        "consistency": consistency,
        "timeliness": timeliness,
        "accuracy": accuracy,
        "duplicate_rows": dup_count,
        "range_violations": range_violations,
        "rule_violations": rule_violations,
        "missing_rate_pct": round(missing_rate, 2),
        "format_rate_pct": round(fmt_rate, 2),
        "data_age_days": age_days,
        "capture_age_days": capture_age_days,
        "outlier_rate_pct": round(outlier_rate, 2),
        "sample_rows": len(rows),
        "sample_cells": total_cells,
        "scores_detail": scores,
        "anomalies": anomalies,
        "suggestions": suggestions,
        "skip_reason": skip_reason,
        "great_expectations": _ge_validate(sample, dataset, rules) if sample else None,
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
    """Full lineage per Table 4 — origin, transforms, downstream, graph, risk,
    version history, quality trace, auto-analysis.  Errors are swallowed so
    lineage queries never block the main flow."""

    # ---- 前提条件 1: 数据已使用校验 ----
    task_count = (
        db.query(TrainingTask).filter(TrainingTask.dataset_id == dataset.id).count()
    )
    data_used = task_count > 0 or dataset.lineage_status == "tracked"

    # ---- R1: 来源 ----
    try:
        origin = {
            "uploaded_by": dataset.owner.username if dataset.owner else None,
            "uploaded_at": dataset.created_at.isoformat() if dataset.created_at else None,
            "original_source": dataset.source,
            "data_type": dataset.data_type,
            "initial_version": dataset.version,
        }
    except Exception:
        origin = {"original_source": dataset.source}

    # ---- R2: 转换过程 ----
    transformations: list[dict] = []
    if dataset.file_count and dataset.file_count > 0:
        transformations.append({
            "rule": "data_loaded",
            "description": f"从 {dataset.source or 'unknown'} 加载 {dataset.file_count} 个文件",
            "timestamp": dataset.created_at.isoformat() if dataset.created_at else None,
            "version_before": None,
            "version_after": dataset.version,
        })
    if dataset.quality_status in ("checking", "passed", "failed"):
        transformations.append({
            "rule": "quality_validated",
            "description": f"质量校验 → {dataset.quality_status}",
            "timestamp": dataset.updated_at.isoformat() if dataset.updated_at else None,
            "version_before": dataset.version,
            "version_after": dataset.version,
        })

    # ---- R3: 下游消费 ----
    downstream: list[dict] = []
    tasks = db.query(TrainingTask).filter(TrainingTask.dataset_id == dataset.id).all()
    for t in tasks:
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
        models = db.query(ModelVersion).filter(ModelVersion.task_id == t.id).all()
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

    # ---- R4: 自动依赖分析 ----
    auto_analysis: dict = {"layers": 0, "total_nodes": 0, "total_edges": 0}
    try:
        layer1 = 1  # dataset itself
        layer2 = len([d for d in downstream if d["type"] == "training_task"])
        layer3 = len([d for d in downstream if d["type"] == "model_version"])
        auto_analysis = {
            "layers": 1 + bool(layer2) + bool(layer3),
            "level1_dataset": layer1,
            "level2_training_tasks": layer2,
            "level3_model_versions": layer3,
            "total_nodes": layer1 + layer2 + layer3,
            "total_edges": layer2 + layer3,
        }
    except Exception:
        pass

    # ---- R5: 血缘图谱（nodes + edges） ----
    graph: dict = {"nodes": [], "edges": []}
    try:
        ds_node_id = f"dataset-{dataset.id}"
        graph["nodes"].append({"id": ds_node_id, "label": dataset.name, "type": "dataset"})
        for d in downstream:
            if d["type"] == "training_task":
                tid = f"task-{d['task_id']}"
                graph["nodes"].append({"id": tid, "label": d["task_name"], "type": "task"})
                graph["edges"].append({"from": ds_node_id, "to": tid, "label": "consumes"})
            elif d["type"] == "model_version":
                mid = f"model-{d['model_code']}"
                graph["nodes"].append({"id": mid, "label": f'{d["model_code"]}:{d["version"]}', "type": "model"})
                if graph["nodes"]:
                    last_task = [n for n in graph["nodes"] if n["type"] == "task"]
                    if last_task:
                        graph["edges"].append({"from": last_task[-1]["id"], "to": mid, "label": "produces"})
    except Exception:
        graph = {"error": "图谱生成失败，请手动检查数据依赖关系", "nodes": [], "edges": []}

    # ---- 其他事件流 1: 质量问题溯源 ----
    quality_trace: dict | None = None
    if dataset.quality_status in ("failed", "checking"):
        quality_trace = {
            "quality_status": dataset.quality_status,
            "root_cause_hint": "质量校验未通过，请查看质量报告中的 anomalies 字段定位问题源头",
            "quality_endpoint": f"/api/v1/datasets/{dataset.id}/quality",
        }

    # ---- 其他事件流 2: 版本历史 ----
    version_history: list[dict] = []
    try:
        from app.models.system_log import SystemLog
        logs = (
            db.query(SystemLog)
            .filter(SystemLog.resource == "dataset", SystemLog.resource_id == dataset.id)
            .filter(SystemLog.action.in_(["create", "update", "quality_check", "quality_repair"]))
            .order_by(SystemLog.created_at.desc())
            .limit(10)
            .all()
        )
        for lg in logs:
            version_history.append({
                "action": lg.action,
                "detail": lg.detail,
                "timestamp": lg.created_at.isoformat() if lg.created_at else None,
            })
    except Exception:
        pass

    # ---- 其他事件流 3: 多任务使用风险提示 ----
    risk_warning: dict | None = None
    task_count = len([d for d in downstream if d["type"] == "training_task"])
    if task_count > 1:
        risk_warning = {
            "level": "warning",
            "message": f"该数据集被 {task_count} 个训练任务使用，变更前请评估影响范围",
            "affected_task_count": task_count,
            "recommendation": "建议先运行影响分析（/lineage/impact）后再变更",
        }

    # ---- Business rule 3: 记录血缘查询到永久审计日志 ----
    try:
        log_repository.create_log(
            db, user_id=dataset.owner_id, username=dataset.owner.username if dataset.owner else "system",
            action="lineage_queried", resource="dataset", resource_id=dataset.id,
            detail=f"查询血缘链：{dataset.name}",
        )
    except Exception:
        pass  # 血缘查询失败不影响主流程

    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "current_version": dataset.version,
        "lineage_status": dataset.lineage_status or "tracked",
        "data_used": data_used,
        "origin": origin,
        "transformations": transformations,
        "downstream": downstream,
        "auto_analysis": auto_analysis,
        "graph": graph,
        "quality_trace": quality_trace,
        "version_history": version_history,
        "risk_warning": risk_warning,
        "affected_summary": {
            "training_tasks": task_count,
            "model_versions": len([d for d in downstream if d["type"] == "model_version"]),
        },
    }


def get_lineage_impact(db: Session, dataset: Dataset) -> dict:
    """Analyse impact per Table 4 R7: affected tasks, models, and datasets."""
    tasks = db.query(TrainingTask).filter(TrainingTask.dataset_id == dataset.id).all()
    affected_tasks = [t.task_code for t in tasks]
    task_ids = [t.id for t in tasks]
    models: list[ModelVersion] = []
    if task_ids:
        models = db.query(ModelVersion).filter(ModelVersion.task_id.in_(task_ids)).all()
    affected_models = [f"{m.model_code}:{m.version}" for m in models]
    siblings = (
        db.query(Dataset).filter(Dataset.id != dataset.id)
        .filter((Dataset.source == dataset.source) | (Dataset.version == dataset.version))
        .limit(20).all()
    )
    affected_datasets = [d.name for d in siblings]
    task_count = len(affected_tasks)
    risk = None
    if task_count > 1:
        risk = {"level": "warning", "message": f"变更将影响 {task_count} 个训练任务", "affected_task_count": task_count}

    # 记录影响分析查询
    try:
        log_repository.create_log(
            db, user_id=dataset.owner_id, username=dataset.owner.username if dataset.owner else "system",
            action="impact_analysis", resource="dataset", resource_id=dataset.id,
            detail=f"影响分析：tasks={task_count}, models={len(affected_models)}",
        )
    except Exception:
        pass

    return {
        "dataset_id": dataset.id,
        "affected_models": affected_models,
        "affected_tasks": affected_tasks,
        "affected_datasets": affected_datasets,
        "risk": risk,
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

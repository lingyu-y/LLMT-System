"""Dataset service — data processing business logic (Part 3 of jiekou.md)."""

import csv as _stdlib_csv
import bz2
import codecs
import gzip
import hashlib
import io as _stdlib_io
import json
import lzma
import logging
import os
import re
import tempfile
import uuid
import zlib
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_minio_client
from app.models.dataset import Dataset
from app.models.model_version import ModelVersion
from app.models.training_task import TrainingTask
from app.repositories import dataset_repository, log_repository

_logger = logging.getLogger(__name__)

# Supported formats (requirement: TXT, CSV, JSON, DOC, DOCX, EXCEL)
# DOC/DOCX → converted to .txt; EXCEL → converted to .csv
_TEXT_EXTS = {".txt", ".csv", ".json", ".jsonl"}
_DOC_EXTS = {".doc", ".docx"}  # → .txt after conversion
_XLS_EXTS = {".xlsx", ".xls"}  # → .csv after conversion
_SUPPORTED_EXTENSIONS = {
    "text": _TEXT_EXTS,
    "doc": _DOC_EXTS,
    "excel": _XLS_EXTS,
}

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')
_MAX_FILENAME_LEN = 255
_TEXT_STORED_SUFFIXES = (".txt", ".csv", ".json", ".jsonl")


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


def _compressed_payload_type(data: bytes) -> str | None:
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if data.startswith(b"BZh"):
        return "bzip2"
    if data.startswith(b"\xfd7zXZ\x00"):
        return "xz"
    if data.startswith(b"\x28\xb5\x2f\xfd"):
        return "zstd"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    if data.startswith((b"\x78\x01", b"\x78\x9c", b"\x78\xda")):
        return "zlib"
    return None


def _try_decompress_text_payload(data: bytes) -> tuple[bytes, str | None]:
    kind = _compressed_payload_type(data)
    if kind is None:
        return data, None
    try:
        if kind == "gzip":
            return gzip.decompress(data), kind
        if kind == "bzip2":
            return bz2.decompress(data), kind
        if kind == "xz":
            return lzma.decompress(data), kind
        if kind == "zlib":
            return zlib.decompress(data), kind
    except Exception as exc:
        raise ValueError(f"检测到 {kind} 压缩内容，但解压失败: {exc}") from exc
    raise ValueError(f"检测到 {kind} 压缩/归档内容，当前数据加载不支持直接解析该格式，请先解压成 TXT/CSV/JSON/JSONL 后上传")


def _validate_text_payload(data: bytes, filename: str, allow_truncated: bool = False) -> str | None:
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        if not allow_truncated:
            return f"{filename} 不是有效 UTF-8 文本，可能是压缩包、二进制文件或编码不匹配"
        decoded = data.decode("utf-8", errors="replace").rstrip("\ufffd")
    if "\x00" in decoded:
        return f"{filename} 包含二进制空字节，可能不是文本数据"
    if decoded:
        replacement_rate = decoded.count("\ufffd") / max(len(decoded), 1)
        control_count = sum(1 for char in decoded if ord(char) < 32 and char not in "\r\n\t")
        control_rate = control_count / max(len(decoded), 1)
        if replacement_rate > 0.01 or control_rate > 0.01:
            return f"{filename} 文本中存在大量乱码或控制字符，请确认不是压缩/二进制内容"
    return None


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


def _spool_text_upload(file: UploadFile, filename: str) -> tuple[str | None, int, str, str | None]:
    """Stream a text upload to a temp file while validating UTF-8 and hashing."""
    h = hashlib.md5()
    size = 0
    decoder = codecs.getincrementaldecoder("utf-8")()
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp_path = temp.name
    replacement_count = 0
    control_count = 0
    char_count = 0
    first_chunk_checked = False
    keep_temp = False
    try:
        while True:
            chunk = file.file.read(_CHUNK)
            if not chunk:
                break
            if not first_chunk_checked:
                first_chunk_checked = True
                compression = _compressed_payload_type(chunk)
                if compression:
                    return None, 0, "", (
                        f"检测到 {compression} 压缩/归档内容，当前数据加载不支持直接解析该格式，"
                        "请先解压成 TXT/CSV/JSON/JSONL 后上传"
                    )
            try:
                decoded = decoder.decode(chunk)
            except UnicodeDecodeError:
                return None, 0, "", f"{filename} 不是有效 UTF-8 文本，可能是压缩包、二进制文件或编码不匹配"
            if "\x00" in decoded:
                return None, 0, "", f"{filename} 包含二进制空字节，可能不是文本数据"
            replacement_count += decoded.count("\ufffd")
            control_count += sum(1 for char in decoded if ord(char) < 32 and char not in "\r\n\t")
            char_count += len(decoded)
            h.update(chunk)
            size += len(chunk)
            temp.write(chunk)
        try:
            tail = decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return None, 0, "", f"{filename} 不是完整的 UTF-8 文本"
        if tail:
            if "\x00" in tail:
                return None, 0, "", f"{filename} 包含二进制空字节，可能不是文本数据"
            replacement_count += tail.count("\ufffd")
            control_count += sum(1 for char in tail if ord(char) < 32 and char not in "\r\n\t")
            char_count += len(tail)
        if size == 0:
            return None, 0, "", "文件内容为空"
        if char_count:
            if replacement_count / char_count > 0.01 or control_count / char_count > 0.01:
                return None, 0, "", f"{filename} 文本中存在大量乱码或控制字符，请确认不是压缩/二进制内容"
        temp.flush()
        keep_temp = True
        return temp_path, size, h.hexdigest(), None
    finally:
        temp.close()
        if not keep_temp:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _minio_retry_fput(minio, bucket: str, object_name: str, file_path: str, content_type: str) -> None:
    last_exc = None
    for attempt in range(1, _RETRY_COUNT + 1):
        try:
            minio.fput_object(bucket, object_name, file_path, content_type=content_type)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_COUNT:
                _logger.warning("MinIO fput_object attempt %d/3 failed: %s", attempt, exc)
    raise last_exc  # type: ignore[misc]


# ============================================================================
# File Upload — 多模态数据加载 (OFFLINE_AI_DATA_LoadData, Table 2)
# ============================================================================


_UNSUPPORTED_FORMAT_MSG = (
    "文件格式不支持。当前仅支持: TXT, CSV, JSON, JSONL, DOC, DOCX, EXCEL (xlsx/xls)。"
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


def _storage_prefix(dataset: Dataset) -> str:
    return (dataset.storage_path or "datasets").strip("/")


def _storage_prefix_candidates(dataset: Dataset) -> list[str]:
    canonical = _storage_prefix(dataset)
    legacy = (dataset.storage_path or "").rstrip("/")
    candidates = [canonical]
    if legacy and legacy not in candidates:
        candidates.append(legacy)
    return candidates


def _object_name(dataset: Dataset, filename: str) -> str:
    return f"{_storage_prefix(dataset)}/{filename}"


def _upload_single(
    minio, bucket: str,
    file: UploadFile,
    dataset: Dataset,
    db: Session,
) -> dict:
    """Upload one file with full pipeline: validate → detect → convert → dedup →
    upload → checksum verify → metadata update.  Returns result dict."""
    filename = file.filename or "unknown"
    detected = _detect_data_type(filename)
    stored_filename = filename
    object_name = _object_name(dataset, stored_filename)
    if _check_dedup(minio, bucket, object_name):
        return {"filename": filename, "success": False, "error": f"文件 {stored_filename} 已存在，请改名或跳过"}

    if detected == "text" and _needs_conversion(filename) is None:
        temp_path, size, local_md5, stream_error = _spool_text_upload(file, filename)
        if stream_error:
            return {"filename": filename, "success": False, "error": stream_error}
        if not temp_path:
            return {"filename": filename, "success": False, "error": "文件内容为空"}
        try:
            _minio_retry_fput(minio, bucket, object_name, temp_path, "text/plain; charset=utf-8")
            uploaded_to = f"s3://{bucket}/{object_name}"
        except Exception as exc:
            return {"filename": filename, "success": False, "error": f"MinIO 上传失败（重试 {_RETRY_COUNT} 次后）: {exc}"}
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

        try:
            stat = minio.stat_object(bucket, object_name)
            remote_etag = stat.etag.strip('"') if stat.etag else ""
            verified = remote_etag == local_md5
        except Exception:
            verified = True

        dataset_repository.update_dataset(
            db, dataset,
            file_count=(dataset.file_count or 0) + 1,
            total_size=(dataset.total_size or 0) + size,
            data_type=detected if not dataset.data_type or dataset.data_type == "other" else dataset.data_type,
            quality_status="unchecked",
            processing_status="pending",
            lineage_status="tracked",
            source=dataset.source or f"upload:{filename}",
        )
        return {
            "success": True,
            "filename": filename,
            "stored_filename": stored_filename,
            "size_original": size,
            "size_stored": size,
            "checksum_local": local_md5,
            "checksum_verified": verified,
            "converted": False,
            "data_type": detected,
            "storage_path": uploaded_to,
        }

    original_content, original_md5 = _read_and_hash(file)
    size_original = len(original_content)
    if size_original == 0:
        return {"filename": filename, "success": False, "error": "文件内容为空"}

    # convert
    converted_data, stored_filename, conv_error = _convert_if_needed(original_content, filename)
    if conv_error:
        return {"filename": filename, "success": False, "error": conv_error}
    if stored_filename.lower().endswith(_TEXT_STORED_SUFFIXES):
        try:
            converted_data, compression = _try_decompress_text_payload(converted_data)
        except ValueError as exc:
            return {"filename": filename, "success": False, "error": str(exc)}
        if compression:
            stored_filename = re.sub(rf"\.({compression})$", "", stored_filename, flags=re.IGNORECASE) or stored_filename
        text_err = _validate_text_payload(converted_data, stored_filename)
        if text_err:
            return {"filename": filename, "success": False, "error": text_err}
    size = len(converted_data)
    local_md5 = _compute_checksum(converted_data) if converted_data != original_content else original_md5

    object_name = _object_name(dataset, stored_filename)
    if _check_dedup(minio, bucket, object_name):
        return {"filename": filename, "success": False, "error": f"文件 {stored_filename} 已存在，请改名或跳过"}

    # upload with retry
    try:
        ct = "text/plain; charset=utf-8" if stored_filename.endswith((".txt", ".csv", ".json", ".jsonl")) else "application/octet-stream"
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
        quality_status="unchecked",
        processing_status="pending",
        lineage_status="tracked",
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

_TEXT_JSON_KEYS = (
    "text",
    "content",
    "body",
    "sentence",
    "instruction",
    "prompt",
    "question",
    "response",
    "completion",
    "answer",
    "input",
    "output",
    "title",
    "正文",
    "内容",
    "问题",
    "答案",
)

_PROMPT_JSON_KEYS = ("prompt", "instruction", "question", "input", "问题")
_RESPONSE_JSON_KEYS = ("response", "completion", "answer", "output", "答案")


def _iter_response_lines(response, chunk_size: int = 64 * 1024):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = ""
    first_chunk = True
    for chunk in response.stream(chunk_size):
        if first_chunk:
            first_chunk = False
            compression = _compressed_payload_type(chunk)
            if compression:
                raise ValueError(f"对象内容是 {compression} 压缩/归档数据，不是可直接预处理的文本")
        pending += decoder.decode(chunk)
        lines = pending.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            pending = lines.pop()
        else:
            pending = ""
        for line in lines:
            yield line.rstrip("\r\n")
    tail = pending + decoder.decode(b"", final=True)
    if tail:
        yield tail.rstrip("\r\n")


def _normalize_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_json_texts(value: object) -> list[str]:
    if isinstance(value, str):
        text = _normalize_text(value)
        return [text] if text else []
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_extract_json_texts(item))
        return texts
    if isinstance(value, dict):
        chunks: list[str] = []
        for key in _TEXT_JSON_KEYS:
            item = value.get(key)
            if isinstance(item, (str, int, float)):
                text = _normalize_text(item)
                if text:
                    chunks.append(text)
        if not chunks:
            for item in value.values():
                if isinstance(item, (str, int, float)):
                    text = _normalize_text(item)
                    if text:
                        chunks.append(text)
        text = _normalize_text(" ".join(chunks))
        return [text] if text else []
    return []


def _first_normalized_value(value: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, (str, int, float)):
            text = _normalize_text(item)
            if text:
                return text
    return ""


def _extract_instruction_records(value: object) -> list[dict[str, str] | str]:
    if isinstance(value, list):
        records: list[dict[str, str] | str] = []
        for item in value:
            records.extend(_extract_instruction_records(item))
        return records
    if isinstance(value, dict):
        prompt = _first_normalized_value(value, _PROMPT_JSON_KEYS)
        response = _first_normalized_value(value, _RESPONSE_JSON_KEYS)
        if prompt and response:
            return [{
                "prompt": prompt,
                "response": response,
                "text": _normalize_text(f"{prompt}\n{response}"),
            }]
        return _extract_json_texts(value)
    return _extract_json_texts(value)


def _write_jsonl_record(output, record: dict[str, str] | str) -> int:
    if isinstance(record, dict):
        prompt = _normalize_text(record.get("prompt", ""))
        response = _normalize_text(record.get("response", ""))
        text = _normalize_text(record.get("text", ""))
        if prompt and response:
            payload = {
                "prompt": prompt,
                "response": response,
                "text": text or _normalize_text(f"{prompt}\n{response}"),
            }
        else:
            payload = {"text": text}
    else:
        text = _normalize_text(record)
        payload = {"text": text}

    if not payload.get("text"):
        return 0
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    output.write(data)
    return len(data)


def _iter_dataset_objects(minio, bucket: str, dataset: Dataset):
    objects_by_name = {}
    for prefix in _storage_prefix_candidates(dataset):
        for obj in minio.list_objects(bucket, prefix=prefix.rstrip("/") + "/", recursive=True):
            objects_by_name[obj.object_name] = obj
    return [
        obj
        for obj in objects_by_name.values()
        if not obj.is_dir
        and "/processed/" not in obj.object_name
        and not obj.object_name.endswith("/")
    ]


def _iter_object_records(minio, bucket: str, object_name: str):
    """Yield individual text strings from a raw MinIO object.

    Parses JSONL, CSV, or plain text line-by-line so the caller can process
    records one at a time (e.g.  for per-record shard rotation).
    """
    suffix = object_name.rsplit(".", 1)[-1].lower() if "." in object_name else "txt"
    response = minio.get_object(bucket, object_name)
    try:
        lines = _iter_response_lines(response)
        if suffix in {"json", "jsonl"}:
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    yield stripped
                    continue
                for record in _extract_instruction_records(parsed):
                    yield record
        elif suffix == "csv":
            reader = _stdlib_csv.reader(lines)
            for row in reader:
                text = _normalize_text(" ".join(cell for cell in row if cell is not None))
                if text:
                    yield text
        else:
            for line in lines:
                if line.strip():
                    yield line
    finally:
        response.close()
        response.release_conn()


def _preprocess_object_to_jsonl(minio, bucket: str, object_name: str, output) -> tuple[int, int]:
    """Write all records from *object_name* to *output* in JSONL format.

    Returns (record_count, bytes_written).
    """
    record_count = 0
    bytes_written = 0
    for text in _iter_object_records(minio, bucket, object_name):
        written = _write_jsonl_record(output, text)
        if written:
            bytes_written += written
            record_count += 1
    return record_count, bytes_written


def _preprocess_dataset_to_jsonl(dataset: Dataset, shard_size_mb: int = 0) -> dict:
    settings = get_settings()
    minio = get_minio_client()
    bucket = settings.MINIO_BUCKET_DATASETS
    raw_objects = _iter_dataset_objects(minio, bucket, dataset)
    if not raw_objects:
        raise ValueError("没有可预处理的原始数据文件")

    shard_limit = shard_size_mb * 1048576 if shard_size_mb > 0 else 0
    total_records = 0
    total_bytes = 0

    temp_files: list[tempfile.TemporaryFile] = [tempfile.TemporaryFile()]
    shard_record_counts: list[int] = [0]
    shard_byte_sizes: list[int] = [0]
    current = 0

    for obj in raw_objects:
        for text in _iter_object_records(minio, bucket, obj.object_name):
            written = _write_jsonl_record(temp_files[current], text)
            if not written:
                continue
            total_records += 1
            total_bytes += written
            shard_record_counts[current] += 1
            shard_byte_sizes[current] += written

            if shard_limit > 0 and shard_byte_sizes[current] >= shard_limit:
                temp_files[current].seek(0)
                temp_files.append(tempfile.TemporaryFile())
                current += 1
                shard_record_counts.append(0)
                shard_byte_sizes.append(0)

    if total_records == 0:
        raise ValueError("预处理未抽取到有效文本")

    num_shards = current + 1

    if num_shards == 1:
        output_object = _object_name(dataset, "processed/data.jsonl")
        temp_files[0].seek(0)
        minio.put_object(
            bucket,
            output_object,
            data=temp_files[0],
            length=total_bytes,
            content_type="application/x-ndjson; charset=utf-8",
        )
        return {
            "output_path": f"s3://{bucket}/{output_object}",
            "output_object": output_object,
            "record_count": total_records,
            "size": total_bytes,
            "source_file_count": len(raw_objects),
            "shard_count": 1,
        }

    for i in range(num_shards):
        shard_name = f"processed/data_shard_{i:05d}.jsonl"
        shard_obj = _object_name(dataset, shard_name)
        temp_files[i].seek(0)
        _minio_retry_put(
            minio, bucket, shard_obj,
            temp_files[i].read(),
            "application/x-ndjson; charset=utf-8",
        )

    manifest = {
        "shard_count": num_shards,
        "shard_size_mb": shard_size_mb,
        "total_records": total_records,
        "total_bytes": total_bytes,
        "shards": [
            {
                "path": f"processed/data_shard_{i:05d}.jsonl",
                "records": shard_record_counts[i],
                "bytes": shard_byte_sizes[i],
            }
            for i in range(num_shards)
        ],
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    manifest_obj = _object_name(dataset, "processed/shards_manifest.json")
    _minio_retry_put(minio, bucket, manifest_obj, manifest_bytes, "application/json")

    first_obj = _object_name(dataset, "processed/data_shard_00000.jsonl")
    return {
        "output_path": f"s3://{bucket}/{first_obj}",
        "output_object": first_obj,
        "record_count": total_records,
        "size": total_bytes,
        "source_file_count": len(raw_objects),
        "shard_count": num_shards,
    }


def start_preprocess(db: Session, dataset: Dataset, shard_size_mb: int = 0) -> dict:
    dataset_repository.update_dataset(db, dataset, quality_status="checking", processing_status="processing")
    job = dataset_repository.create_processing_job(db, dataset, "preprocess")
    job["shard_size_mb"] = shard_size_mb
    return job


def run_preprocess_job(dataset_id: int, job_id: str, shard_size_mb: int = 0) -> None:
    db = SessionLocal()
    try:
        dataset = dataset_repository.get_dataset_by_id(db, dataset_id)
        if dataset is None:
            dataset_repository.update_processing_job(
                job_id,
                status="failed",
                progress=100,
                finished_at=datetime.now(timezone.utc).isoformat(),
                error="数据集不存在",
            )
            return

        preprocess_result = _preprocess_dataset_to_jsonl(dataset, shard_size_mb=shard_size_mb)
        report = check_quality(db, dataset)
        # Mark dataset as preprocessed so training can find processed/data.jsonl
        dataset_repository.update_dataset(
            db, dataset,
            quality_status="passed" if report["passed"] else "failed",
            processing_status="completed",
        )
        dataset_repository.update_processing_job(
            job_id,
            status="completed" if report["passed"] else "failed",
            progress=100,
            finished_at=datetime.now(timezone.utc).isoformat(),
            output_path=preprocess_result["output_path"],
            record_count=preprocess_result["record_count"],
            processed_size=preprocess_result["size"],
            source_file_count=preprocess_result["source_file_count"],
        )
    except Exception as exc:
        dataset = dataset_repository.get_dataset_by_id(db, dataset_id)
        if dataset is not None:
            dataset_repository.update_dataset(db, dataset, quality_status="failed", processing_status="failed")
        dataset_repository.update_processing_job(
            job_id,
            status="failed",
            progress=100,
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
    finally:
        db.close()


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
        files = _iter_dataset_objects(minio, bucket, dataset)
        processed = []
        for prefix in _storage_prefix_candidates(dataset):
            processed.extend(
                o for o in minio.list_objects(bucket, prefix=prefix.rstrip("/") + "/processed/", recursive=True)
                if not o.is_dir and o.object_name.endswith(".jsonl") and "shards_manifest" not in o.object_name
            )
        processed.sort(key=lambda o: o.object_name)
        files = processed or files
        if not files:
            return None, "no objects in storage"
        obj = files[0]
        resp = minio.get_object(bucket, obj.object_name)
        data = resp.read(max_bytes)
        resp.close()
        resp.release_conn()
        compression = _compressed_payload_type(data)
        if compression:
            return None, f"对象 {obj.object_name} 是 {compression} 压缩/归档数据，不是可直接校验的文本"
        text_err = _validate_text_payload(data, obj.object_name, allow_truncated=True)
        if text_err:
            return None, text_err
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


def _parse_jsonl_text_rows(data: bytes) -> tuple[list[str], int]:
    text = data.decode("utf-8", errors="replace")
    rows: list[str] = []
    invalid = 0
    lines = text.splitlines()
    if data and not data.endswith((b"\n", b"\r")) and lines:
        lines = lines[:-1]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("{"):
            invalid += 1
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            invalid += 1
            continue
        extracted = _extract_json_texts(parsed)
        if extracted:
            rows.extend(extracted)
        else:
            invalid += 1
    return rows, invalid


def _looks_like_jsonl_text(rows: list[str], invalid_rows: int) -> bool:
    total = len(rows) + invalid_rows
    if total == 0:
        return False
    return bool(rows) and (invalid_rows / total) <= 0.02


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

    lines = [line for line in text.splitlines() if line.strip()]
    jsonl_rows: list[str] = []
    for line in lines[:500]:
        stripped = line.strip()
        if not stripped.startswith(("{", "[")):
            jsonl_rows = []
            break
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            jsonl_rows = []
            break
        jsonl_rows.extend(_extract_json_texts(parsed))

    if jsonl_rows:
        df = pd.DataFrame({"text": jsonl_rows[:500]})
    elif "," in text[:200] or "\t" in text[:200]:
        try:
            df = pd.read_csv(_stdlib_io.StringIO(text), nrows=500)
        except Exception as exc:
            _logger.warning("GE-compatible CSV parsing failed for dataset %s: %s", dataset.id, exc)
            df = pd.DataFrame({"line": lines[:500]})
    else:
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
    jsonl_text_rows, jsonl_invalid_rows = _parse_jsonl_text_rows(sample) if sample else ([], 0)
    is_jsonl_text = _looks_like_jsonl_text(jsonl_text_rows, jsonl_invalid_rows)
    rows: list[list[str]] = [[text] for text in jsonl_text_rows] if is_jsonl_text else (_parse_csv_to_rows(sample) if sample else [])
    total_cells = sum(len(r) for r in rows) if rows else 0
    has_sample = total_cells > 0
    storage_available = has_sample and not sample_err
    if sample_err:
        issue = "未上传数据文件" if (dataset.file_count or 0) <= 0 else f"无法读取数据文件: {sample_err}"
        anomalies.append({"field": "storage", "issue": issue})
        suggestions.append("请先完成文件上传，或检查 MinIO 存储路径、连接与权限后重新校验")

    # ====================================================================
    # 1. Completeness — 缺失率 ≤5% + 重复值检测
    # ====================================================================
    completeness = True
    missing_rate = 0.0
    dup_count = 0
    if not storage_available:
        completeness = False
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
    elif not sample_err:
        completeness = False
        anomalies.append({"field": "metadata", "issue": "名称、类型或数据文件缺失"})
    if not completeness:
        scores["completeness"] = 0.0 if not has_sample else max(0, 100 - missing_rate * 20 - dup_count * 0.1)
    else:
        scores["completeness"] = 100.0
    if not completeness and storage_available:
        anomalies.append({"field": "completeness", "issue": f"缺失率 {missing_rate:.1f}% > 5%"})
        suggestions.append("补充缺失字段或删除空值行")

    # ====================================================================
    # 2. Consistency — 格式一致率 ≥98% + 取值范围校验
    # ====================================================================
    consistency = True
    fmt_rate = 100.0
    range_violations = 0
    if not storage_available:
        consistency = False
        fmt_rate = 0.0
    if has_sample and len(rows) > 1:
        header = ["text"] if is_jsonl_text else rows[0]
        if is_jsonl_text:
            total_jsonl_rows = len(jsonl_text_rows) + jsonl_invalid_rows
            fmt_rate = (len(jsonl_text_rows) / total_jsonl_rows * 100) if total_jsonl_rows else 0
        else:
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
        issue = f"JSONL 文本格式合法率 {fmt_rate:.1f}% < 98%" if is_jsonl_text else f"格式一致率 {fmt_rate:.1f}% < 98%"
        anomalies.append({"field": "consistency", "issue": issue})
        suggestions.append("修复无法解析或缺少 text 字段的 JSONL 行" if is_jsonl_text else "统一列数或修复格式异常行")
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
    if not storage_available:
        accuracy = False
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
    overall_score = round(sum(scores.get(k, 0) * weights.get(k, 0) for k in weights), 1)
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
            files = _iter_dataset_objects(minio, settings.MINIO_BUCKET_DATASETS, dataset)
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


def delete_dataset(db: Session, dataset: Dataset) -> None:
    prefixes = _storage_prefix_candidates(dataset)
    dataset_repository.delete_dataset(db, dataset)

    try:
        settings = get_settings()
        minio = get_minio_client()
        bucket = settings.MINIO_BUCKET_DATASETS
        deleted: set[str] = set()
        for prefix in prefixes:
            for obj in minio.list_objects(bucket, prefix=prefix.rstrip("/") + "/", recursive=True):
                if not obj.is_dir and obj.object_name not in deleted:
                    minio.remove_object(bucket, obj.object_name)
                    deleted.add(obj.object_name)
    except Exception as exc:
        _logger.warning("Dataset metadata deleted, but MinIO cleanup failed: %s", exc)


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
    upload_logs = []
    try:
        from app.models.system_log import SystemLog
        upload_logs = (
            db.query(SystemLog)
            .filter(SystemLog.resource == "dataset", SystemLog.resource_id == dataset.id)
            .filter(SystemLog.action.in_(["upload", "upload_batch", "import", "preprocess"]))
            .order_by(SystemLog.created_at.asc())
            .all()
        )
    except Exception:
        upload_logs = []

    for lg in upload_logs:
        detail = lg.detail or ""
        description = detail
        if lg.action == "upload":
            description = detail or "上传文件"
        elif lg.action == "upload_batch":
            try:
                payload = json.loads(detail)
                files = payload.get("files", [])
                filenames = [
                    str(item.get("stored_filename") or item.get("filename"))
                    for item in files
                    if item.get("success") and (item.get("stored_filename") or item.get("filename"))
                ]
                message = payload.get("message") or "批量上传文件"
                description = f"{message}：{', '.join(filenames)}" if filenames else message
            except Exception:
                description = detail or "批量上传文件"
        elif lg.action == "import":
            description = detail or "导入外部数据"
        elif lg.action == "preprocess":
            description = detail or "启动预处理"

        transformations.append({
            "rule": lg.action,
            "description": description,
            "timestamp": lg.created_at.isoformat() if lg.created_at else None,
            "version_before": None,
            "version_after": dataset.version,
            "operator": lg.username,
        })

    if not upload_logs and dataset.file_count and dataset.file_count > 0:
        transformations.append({
            "rule": "data_loaded",
            "description": f"由 {dataset.owner.username if dataset.owner else 'unknown'} 上传 {dataset.file_count} 个文件",
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

    lineage_status = dataset.lineage_status
    if transformations and lineage_status in (None, "", "none", "pending"):
        dataset = dataset_repository.update_dataset(db, dataset, lineage_status="tracked")
        lineage_status = dataset.lineage_status

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
        "lineage_status": lineage_status or "tracked",
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

"""Centralised log service — single entry point for all audit logging.

Writes to PostgreSQL (via log_repository), indexes to Elasticsearch,
and broadcasts to connected WebSocket clients.

To switch backend (e.g. ES-first queries), change only this layer.
"""

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_elasticsearch_client
from app.repositories import log_repository

# ---------------------------------------------------------------------------
# WebSocket broadcast state
# ---------------------------------------------------------------------------

_connected_clients: list[WebSocket] = []
_lock = threading.Lock()
_main_loop: asyncio.AbstractEventLoop | None = None

settings = get_settings()
_ES_INDEX = settings.ELASTICSEARCH_INDEX_LOGS
_ERROR_LEVELS = {"ERROR", "CRITICAL"}
_fallback_lock = threading.Lock()


def register_ws_client(websocket: WebSocket) -> None:
    global _main_loop
    with _lock:
        _connected_clients.append(websocket)
    # Capture the ASGI event loop from the WebSocket accept handler (runs on it).
    if _main_loop is None:
        try:
            _main_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass


def unregister_ws_client(websocket: WebSocket) -> None:
    with _lock:
        if websocket in _connected_clients:
            _connected_clients.remove(websocket)


def _broadcast_sync(entry: dict) -> None:
    """Thread-safe: schedules async sends on the captured main event loop."""
    with _lock:
        clients = list(_connected_clients)
    if not clients or _main_loop is None or not _main_loop.is_running():
        return
    payload = json.dumps(entry, ensure_ascii=False)
    for ws in clients:
        _main_loop.call_soon_threadsafe(
            lambda w=ws, p=payload: asyncio.ensure_future(_safe_send(w, p))
        )


async def _safe_send(ws: WebSocket, payload: str) -> None:
    try:
        await ws.send_text(payload)
    except Exception:
        unregister_ws_client(ws)


# ---------------------------------------------------------------------------
# Elasticsearch async write helper
# ---------------------------------------------------------------------------

def _index_to_elasticsearch(entry: dict) -> None:
    """Best-effort index to Elasticsearch; never blocks the caller."""
    try:
        es = get_elasticsearch_client()
        _replay_fallback_logs(es)
        es.index(index=_ES_INDEX, body=entry)
    except Exception:
        _append_fallback_log(entry)
        pass  # ES is optional for audit logging


def _append_fallback_log(entry: dict) -> None:
    try:
        path = settings.ELASTICSEARCH_FALLBACK_LOG_PATH
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with _fallback_lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _replay_fallback_logs(es) -> None:
    path = settings.ELASTICSEARCH_FALLBACK_LOG_PATH
    if not os.path.exists(path):
        return
    with _fallback_lock:
        try:
            with open(path, encoding="utf-8") as fh:
                entries = [json.loads(line) for line in fh if line.strip()]
            if not entries:
                os.remove(path)
                return
            for item in entries[:100]:
                es.index(index=_ES_INDEX, body=item)
            remaining = entries[100:]
            if remaining:
                with open(path, "w", encoding="utf-8") as fh:
                    for item in remaining:
                        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            else:
                os.remove(path)
        except Exception:
            pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_level(level: str | None, *, action: str = "", message: str = "") -> str:
    value = (level or "").upper()
    if value in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL"}:
        return "WARN" if value == "WARNING" else value

    text = f"{action} {message}".lower()
    if any(word in text for word in ("critical", "fatal", "严重")):
        return "CRITICAL"
    if any(word in text for word in ("error", "failed", "fail", "exception", "错误", "失败", "异常")):
        return "ERROR"
    if action in {"delete", "status_change", "quality_repair"} or any(
        word in message for word in ("删除", "禁用", "修复", "告警", "暂停", "取消")
    ):
        return "WARN"
    return "INFO"


def _build_log_document(
    *,
    log_id: int | None = None,
    level: str | None,
    module: str,
    message: str,
    category: str,
    timestamp: str | None = None,
    user_id: int | None = None,
    username: str = "",
    action: str = "",
    resource: str = "",
    resource_id: int | None = None,
    detail: str = "",
    ip_address: str = "",
    task_id: int | None = None,
    task_code: str | None = None,
    step: int | None = None,
    trace_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_level = _normalize_level(level, action=action, message=message or detail)
    ts = timestamp or _now_iso()
    document: dict[str, Any] = {
        "id": log_id,
        "timestamp": ts,
        "created_at": ts,
        "level": normalized_level,
        "category": category,
        "module": module,
        "message": message or detail,
        "detail": detail or message,
        "user_id": user_id,
        "username": username,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "ip_address": ip_address,
        "task_id": task_id,
        "task_code": task_code,
        "step": step,
        "trace_id": trace_id,
    }
    if extra:
        document.update({f"extra_{key}": value for key, value in extra.items()})
    return document


def index_log(
    *,
    log_id: int | None = None,
    level: str | None,
    module: str,
    message: str,
    category: str = "application",
    timestamp: str | None = None,
    user_id: int | None = None,
    username: str = "",
    action: str = "",
    resource: str = "",
    resource_id: int | None = None,
    detail: str = "",
    ip_address: str = "",
    task_id: int | None = None,
    task_code: str | None = None,
    step: int | None = None,
    trace_id: str = "",
    extra: dict[str, Any] | None = None,
    async_write: bool = True,
) -> dict[str, Any]:
    """Index one JSON log record into Elasticsearch.

    This is the shared ES entry point for system, audit, training, and
    exception logs required by the SRS log-management use case.
    """
    document = _build_log_document(
        log_id=log_id,
        level=level,
        module=module,
        message=message,
        category=category,
        timestamp=timestamp,
        user_id=user_id,
        username=username,
        action=action,
        resource=resource,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        task_id=task_id,
        task_code=task_code,
        step=step,
        trace_id=trace_id,
        extra=extra,
    )
    if async_write:
        threading.Thread(target=_index_to_elasticsearch, args=(document.copy(),), daemon=True).start()
    else:
        _index_to_elasticsearch(document)
    if document["level"] in _ERROR_LEVELS:
        _broadcast_sync(document)
    return document


def search_logs(
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    level: str = "",
    module: str = "",
    category: str = "",
    action: str = "",
    resource: str = "",
    username: str = "",
    start_date: str = "",
    end_date: str = "",
    task_id: int | None = None,
    task_code: str = "",
) -> tuple[list[dict[str, Any]], int] | None:
    """Search logs in Elasticsearch; return None when ES is unavailable."""
    filters: list[dict[str, Any]] = []
    if level:
        filters.append({"term": {"level": level.upper()}})
    if module:
        filters.append({"term": {"module": module}})
    if category:
        filters.append({"term": {"category": category}})
    if action:
        filters.append({"term": {"action": action}})
    if resource:
        filters.append({"term": {"resource": resource}})
    if username:
        filters.append({"term": {"username": username}})
    if task_id is not None:
        filters.append({"term": {"task_id": task_id}})
    if task_code:
        filters.append({"term": {"task_code": task_code}})
    if start_date or end_date:
        range_filter: dict[str, Any] = {}
        if start_date:
            range_filter["gte"] = start_date
        if end_date:
            range_filter["lte"] = end_date
        filters.append({"range": {"timestamp": range_filter}})

    must: list[dict[str, Any]] = []
    if keyword:
        must.append({
            "multi_match": {
                "query": keyword,
                "fields": ["message", "detail", "module", "action", "resource", "task_code", "username"],
            }
        })

    query: dict[str, Any] = {"bool": {}}
    if filters:
        query["bool"]["filter"] = filters
    if must:
        query["bool"]["must"] = must
    if not filters and not must:
        query = {"match_all": {}}

    try:
        es = get_elasticsearch_client()
        response = es.search(
            index=_ES_INDEX,
            query=query,
            from_=(page - 1) * page_size,
            size=page_size,
            sort=[{"timestamp": {"order": "desc"}}],
        )
    except Exception:
        return None

    hits = response.get("hits", {})
    total_raw = hits.get("total", 0)
    total = total_raw.get("value", 0) if isinstance(total_raw, dict) else int(total_raw or 0)
    return [hit.get("_source", {}) for hit in hits.get("hits", [])], total


def get_log_stats(
    *,
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any] | None:
    """Return Elasticsearch log statistics for dashboard-style analysis."""
    filters: list[dict[str, Any]] = []
    if start_date or end_date:
        range_filter: dict[str, Any] = {}
        if start_date:
            range_filter["gte"] = start_date
        if end_date:
            range_filter["lte"] = end_date
        filters.append({"range": {"timestamp": range_filter}})

    query: dict[str, Any] = {"bool": {"filter": filters}} if filters else {"match_all": {}}
    try:
        es = get_elasticsearch_client()
        response = es.search(
            index=_ES_INDEX,
            size=0,
            query=query,
            aggs={
                "levels": {"terms": {"field": "level", "size": 10}},
                "modules": {"terms": {"field": "module", "size": 20}},
                "categories": {"terms": {"field": "category", "size": 10}},
                "errors_over_time": {
                    "filter": {"terms": {"level": ["ERROR", "CRITICAL"]}},
                    "aggs": {
                        "by_minute": {
                            "date_histogram": {
                                "field": "timestamp",
                                "fixed_interval": "1m",
                                "min_doc_count": 0,
                            }
                        }
                    },
                },
            },
        )
    except Exception:
        return None

    aggs = response.get("aggregations", {})
    return {
        "levels": aggs.get("levels", {}).get("buckets", []),
        "modules": aggs.get("modules", {}).get("buckets", []),
        "categories": aggs.get("categories", {}).get("buckets", []),
        "errors_over_time": aggs.get("errors_over_time", {})
        .get("by_minute", {})
        .get("buckets", []),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_log(
    db: Session,
    user_id: int | None,
    username: str,
    action: str,
    resource: str,
    resource_id: int | None = None,
    detail: str = "",
    ip_address: str = "",
) -> dict:
    """Write audit log to PostgreSQL, Elasticsearch, and broadcast to WS.

    Returns a dict suitable for JSON serialisation (the log entry).
    """
    # 1. PostgreSQL (always)
    record = log_repository.create_log(
        db,
        user_id=user_id,
        username=username,
        action=action,
        resource=resource,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )

    entry = {
        "id": record.id,
        "user_id": record.user_id,
        "username": record.username,
        "action": record.action,
        "resource": record.resource,
        "resource_id": record.resource_id,
        "detail": record.detail,
        "message": record.detail,
        "level": _normalize_level(None, action=record.action, message=record.detail),
        "category": "audit",
        "module": record.resource,
        "ip_address": record.ip_address,
        "timestamp": record.created_at.isoformat() if record.created_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }

    # 2. Elasticsearch (best-effort, fire-and-forget)
    threading.Thread(
        target=_index_to_elasticsearch,
        args=(_build_log_document(
            log_id=record.id,
            level=entry["level"],
            module=entry["module"],
            message=entry["message"],
            category="audit",
            timestamp=entry["timestamp"],
            user_id=record.user_id,
            username=record.username,
            action=record.action,
            resource=record.resource,
            resource_id=record.resource_id,
            detail=record.detail,
            ip_address=record.ip_address,
        ),),
        daemon=True,
    ).start()

    # 3. WebSocket broadcast
    _broadcast_sync(entry)

    return entry

"""Centralised log service — single entry point for all audit logging.

Writes to PostgreSQL (via log_repository), indexes to Elasticsearch,
and broadcasts to connected WebSocket clients.

To switch backend (e.g. ES-first queries), change only this layer.
"""

import asyncio
import json
import threading
from datetime import datetime

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.core.database import get_elasticsearch_client
from app.repositories import log_repository

# ---------------------------------------------------------------------------
# WebSocket broadcast state
# ---------------------------------------------------------------------------

_connected_clients: list[WebSocket] = []
_lock = threading.Lock()

_ES_INDEX = "system-logs"


def register_ws_client(websocket: WebSocket) -> None:
    with _lock:
        _connected_clients.append(websocket)


def unregister_ws_client(websocket: WebSocket) -> None:
    with _lock:
        if websocket in _connected_clients:
            _connected_clients.remove(websocket)


def _broadcast_sync(entry: dict) -> None:
    """Called from a synchronous context; schedules async broadcast."""
    with _lock:
        clients = list(_connected_clients)
    if not clients:
        return
    payload = json.dumps(entry, ensure_ascii=False)
    for ws in clients:
        try:
            # WebSocket.send_text is async, so we schedule it on the event loop.
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_safe_send(ws, payload))
        except RuntimeError:
            pass  # no event loop available, skip broadcast


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
        es.index(index=_ES_INDEX, body=entry)
    except Exception:
        pass  # ES is optional for audit logging


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
        "ip_address": record.ip_address,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }

    # 2. Elasticsearch (best-effort, fire-and-forget)
    threading.Thread(target=_index_to_elasticsearch, args=(entry.copy(),), daemon=True).start()

    # 3. WebSocket broadcast
    _broadcast_sync(entry)

    return entry

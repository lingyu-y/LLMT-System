"""Dashboard / monitoring endpoints — 仪表盘/监控大屏 (Part 2 of jiekou.md)."""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories import dashboard_repository

router = APIRouter(prefix="/dashboard", tags=["监控大屏"])


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return success_response(dashboard_repository.get_summary(db))


@router.get("/metrics")
def dashboard_metrics(
    _current_user: User = Depends(get_current_user),
):
    return success_response(dashboard_repository.get_metrics())


@router.get("/training-tasks")
def dashboard_training_tasks(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    tasks = dashboard_repository.get_training_tasks(db)
    return success_response(tasks)


@router.get("/activities")
def dashboard_activities(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return success_response(dashboard_repository.get_activities(db, limit=limit))


@router.get("/alerts")
def dashboard_alerts(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return success_response(dashboard_repository.get_alerts(db, limit=limit))


@router.websocket("/stream")
async def dashboard_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
            payload = {
                "summary": {"running_tasks": 0, "gpu_utilization": 72.5, "updated_at": datetime.now().isoformat()},
                "alerts": [],
            }
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass

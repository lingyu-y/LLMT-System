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
    range: str = Query("1h", description="时间范围: 15m / 1h / 6h / 24h"),
    _current_user: User = Depends(get_current_user),
):
    valid_ranges = {"15m", "1h", "6h", "24h"}
    if range not in valid_ranges:
        range = "1h"
    return success_response(dashboard_repository.get_metrics(range_str=range))


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
            # 每个连接独立 DB session
            db = next(get_db())
            try:
                summary = dashboard_repository.get_summary(db)
                training_tasks = dashboard_repository.get_training_tasks(db)
                alerts = dashboard_repository.get_alerts(db, limit=5)
                metrics = dashboard_repository.get_metrics(range_str="1h")
            finally:
                db.close()

            payload = {
                "summary": summary,
                "training_tasks": training_tasks,
                "alerts": alerts,
                "metrics": {
                    "loss": metrics["loss"][-10:],
                    "accuracy": metrics["accuracy"][-10:],
                    "gpu_utilization": metrics["gpu_utilization"][-10:],
                    "gpu_memory": metrics["gpu_memory"][-10:],
                    "latency": metrics["latency"][-10:],
                },
                "updated_at": datetime.now().isoformat(),
            }
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass

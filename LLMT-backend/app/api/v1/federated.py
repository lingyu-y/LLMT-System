"""Federated learning API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.db import get_db
from app.schemas.federated import (
    AddParticipantRequest,
    FederatedTaskCreate,
    RemoveParticipantRequest,
)
from app.services import federated_service

router = APIRouter(prefix="/federated", tags=["联邦学习"])


@router.post("/tasks")
def create_federated_task(
    body: FederatedTaskCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new federated learning task."""
    result = federated_service.create_task(db, body, creator_id=user.id)
    return success_response(result.model_dump(), "联邦学习任务已创建")


@router.get("/tasks")
def list_federated_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str = Query("", alias="status"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """List federated learning tasks with pagination."""
    items, total = federated_service.list_tasks(
        db, page=page, page_size=page_size, status=status_filter,
    )
    return paginated_response(
        [item.model_dump() for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}")
def get_federated_task(
    task_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get a federated learning task by ID."""
    result = federated_service.get_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="联邦学习任务不存在")
    return success_response(result.model_dump())


@router.post("/tasks/{task_id}/start")
def start_federated_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Start a federated learning task."""
    result = federated_service.start_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="任务不存在或状态不允许启动")
    return success_response(result.model_dump(), "联邦学习任务已启动")


@router.post("/tasks/{task_id}/cancel")
def cancel_federated_task(
    task_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Cancel a running federated learning task."""
    result = federated_service.cancel_task(db, task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="任务不存在或状态不允许取消")
    return success_response(result.model_dump(), "联邦学习任务已取消")


@router.get("/tasks/{task_id}/metrics")
def get_federated_metrics(
    task_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get training metrics for a federated learning task."""
    metrics = federated_service.get_task_metrics(db, task_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="任务不存在")
    return success_response(metrics)


@router.get("/tasks/{task_id}/logs")
def get_federated_logs(
    task_id: int,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Get training logs for a federated learning task."""
    logs = federated_service.get_task_logs(db, task_id)
    return success_response({"task_id": task_id, "logs": logs, "total": len(logs)})


@router.post("/tasks/{task_id}/participants")
def add_participant(
    task_id: int,
    body: AddParticipantRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Add a participant to a federated learning task (dynamic join)."""
    result = federated_service.add_participant(db, task_id, body)
    if result is None:
        raise HTTPException(status_code=409, detail="任务不存在或参与方ID已存在")
    return success_response(result.model_dump(), "参与方已加入")


@router.delete("/tasks/{task_id}/participants/{participant_id}")
def remove_participant(
    task_id: int,
    participant_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Remove a participant from a federated learning task (dynamic leave)."""
    success = federated_service.remove_participant(db, task_id, participant_id)
    if not success:
        raise HTTPException(status_code=404, detail="参与方不存在")
    return success_response(None, "参与方已移除")


@router.get("/options")
def get_federated_options(
    _user=Depends(get_current_user),
):
    """Get available options for federated learning configuration."""
    return success_response({
        "aggregation_strategies": [
            {"value": "fedavg", "label": "FedAvg (均匀平均)"},
            {"value": "weighted_fedavg", "label": "加权 FedAvg (按数据量加权)"},
            {"value": "fedprox", "label": "FedProx (近端优化)"},
        ],
        "model_types": [
            {"value": "gpt2", "label": "GPT-2"},
            {"value": "bert", "label": "BERT"},
        ],
        "dp_algorithms": [
            {"value": "dp-sgd", "label": "DP-SGD (差分隐私SGD)"},
        ],
    })

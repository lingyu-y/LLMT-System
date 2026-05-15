"""SystemLog repository."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.system_log import SystemLog


def create_log(
    db: Session,
    user_id: int | None,
    username: str,
    action: str,
    resource: str,
    resource_id: int | None = None,
    detail: str = "",
    ip_address: str = "",
) -> SystemLog:
    log = SystemLog(
        user_id=user_id,
        username=username,
        action=action,
        resource=resource,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_logs(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    action: str = "",
    resource: str = "",
    username: str = "",
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[SystemLog], int]:
    q = db.query(SystemLog)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            SystemLog.detail.ilike(like) | SystemLog.action.ilike(like)
        )
    if action:
        q = q.filter(SystemLog.action == action)
    if resource:
        q = q.filter(SystemLog.resource == resource)
    if username:
        q = q.filter(SystemLog.username.ilike(f"%{username}%"))
    if start_date:
        q = q.filter(SystemLog.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        q = q.filter(SystemLog.created_at <= datetime.fromisoformat(end_date))
    total = q.count()
    logs = (
        q.order_by(SystemLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return logs, total


def get_user_logs(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SystemLog], int]:
    q = db.query(SystemLog).filter(SystemLog.user_id == user_id)
    total = q.count()
    logs = (
        q.order_by(SystemLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return logs, total

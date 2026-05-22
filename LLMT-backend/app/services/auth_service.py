"""Auth service."""

import logging

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginResponse, UserInfo

logger = logging.getLogger(__name__)


def _log_auth_event(db: Session, action: str, username: str, user_id: int | None, detail: str, request: Request | None = None):
    """Record login/logout/register events to system_log."""
    try:
        from app.services import log_service
        ip = request.client.host if request and request.client else ""
        log_service.create_log(
            db, user_id=user_id, username=username,
            action=action, resource="auth", resource_id=user_id,
            detail=detail, ip_address=ip,
        )
    except Exception:
        pass


def authenticate_user(
    db: Session,
    username: str,
    password: str,
    request: Request | None = None,
) -> LoginResponse:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("Login failed: user %s not found", username)
        _log_auth_event(db, "login_failed", username, None, f"用户不存在: {username}", request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(password, user.password_hash):
        logger.warning("Login failed: bad password for user %s", username)
        _log_auth_event(db, "login_failed", username, user.id, "密码错误", request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status != "active":
        logger.warning("Login failed: user %s status is %s", username, user.status)
        _log_auth_event(db, "login_blocked", username, user.id, f"账号状态: {user.status}", request)
        raise HTTPException(status_code=403, detail="账号已被禁用")

    role_codes = [role.name for role in user.roles]
    menu_keys = list({menu.key for role in user.roles for menu in role.menus})

    token = create_access_token({"sub": str(user.id), "username": user.username})

    _log_auth_event(db, "login_success", username, user.id, "登录成功", request)

    return LoginResponse(
        token=token,
        user=UserInfo(
            id=user.id,
            username=user.username,
            realName=user.real_name,
            roleCodes=role_codes,
            menuKeys=menu_keys,
        ),
    )

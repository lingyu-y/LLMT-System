"""Auth service."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginResponse, UserInfo


def authenticate_user(db: Session, username: str, password: str) -> LoginResponse:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="账号已被禁用")

    role_codes = [role.name for role in user.roles]
    menu_keys = list({menu.key for role in user.roles for menu in role.menus})

    token = create_access_token({"sub": str(user.id), "username": user.username})

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

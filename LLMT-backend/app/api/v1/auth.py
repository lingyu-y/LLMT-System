"""Auth API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.role import Role
from app.models.user import User
from app.core.security import create_access_token
from app.schemas.auth import DemoAccount, LoginRequest, LoginResponse, RefreshResponse, RegisterRequest
from app.repositories import user_repository
from app.services.auth_service import authenticate_user

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    return authenticate_user(db, request.username, request.password)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    if user_repository.get_user_by_username(db, request.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    role = db.query(Role).filter(Role.name == "user").first()
    role_ids = [role.id] if role else []
    user_repository.create_user(
        db,
        username=request.username,
        password=request.password,
        real_name=request.realName,
        email=request.email,
        phone=request.phone,
        role_ids=role_ids,
    )
    return authenticate_user(db, request.username, request.password)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    return success_response(message="已退出登录")


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    role_codes = [role.name for role in current_user.roles]
    menu_keys = list({menu.key for role in current_user.roles for menu in role.menus})
    return success_response({
        "id": current_user.id,
        "username": current_user.username,
        "realName": current_user.real_name,
        "roleCodes": role_codes,
        "menuKeys": menu_keys,
    })


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.status == "active").all()
    result: list[DemoAccount] = []
    for u in users:
        role_codes = [role.name for role in u.roles]
        result.append(DemoAccount(username=u.username, realName=u.real_name, roleCodes=role_codes))
    return result


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(current_user: User = Depends(get_current_user)):
    token = create_access_token({"sub": str(current_user.id), "username": current_user.username})
    return {"token": token}

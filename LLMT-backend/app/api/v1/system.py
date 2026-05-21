"""System management endpoints -- users, roles, menus, permissions, logs."""

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories import log_repository, user_repository  # log_repository used for queries only
from app.services import log_service  # log_service is the single write entry-point
from app.schemas.user import (
    UserCreate,
    UserListOut,
    UserOut,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)

router = APIRouter(prefix="/system", tags=["系统管理"])

# ============================================================================
# 用户管理
# ============================================================================

@router.get("/users")
def list_users(    
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索用户名/姓名/邮箱"),
    status_filter: str | None = Query(None, alias="status", description="active | locked | disabled"),
    db=Depends(get_db),
    _admin=Depends(require_admin),
):
    users, total = user_repository.get_users(
        db, page=page, page_size=page_size, keyword=keyword, status=status_filter
    )
    data = [UserListOut.model_validate(u) for u in users]
    return paginated_response(data, total, page, page_size)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(    
    body: UserCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if user_repository.get_user_by_username(db, body.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    user = user_repository.create_user(
        db,
        username=body.username,
        password=body.password,
        real_name=body.real_name,
        email=body.email,
        phone=body.phone,
        role_ids=body.role_ids,
    )
    log_service.create_log(
        db, user_id=None, username="admin",
        action="create", resource="user", resource_id=user.id,
        detail=f"创建用户 {user.username}",
    )
    return success_response(UserOut.model_validate(user), "用户创建成功")


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return success_response(UserOut.model_validate(user))


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if body.username and body.username != user.username:
        existing = user_repository.get_user_by_username(db, body.username)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    user = user_repository.update_user(db, user, **body.model_dump(exclude_unset=True))
    log_service.create_log(
        db, user_id=None, username="admin",
        action="update", resource="user", resource_id=user.id,
        detail=f"修改用户 {user.username}",
    )
    return success_response(UserOut.model_validate(user), "用户修改成功")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user_repository.delete_user(db, user)
    log_service.create_log(
        db, user_id=None, username="admin",
        action="delete", resource="user", resource_id=user_id,
        detail=f"删除用户 {user.username}",
    )
    return success_response(message="用户删除成功")


@router.patch("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user = user_repository.set_user_status(db, user, body.status)
    log_service.create_log(
        db, user_id=None, username="admin",
        action="status_change", resource="user", resource_id=user.id,
        detail=f"修改用户 {user.username} 状态为 {body.status}",
    )
    return success_response(UserOut.model_validate(user), "用户状态已更新")


@router.put("/users/{user_id}/roles")
def update_user_roles(
    user_id: int,
    body: UserRoleUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    user = user_repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user = user_repository.set_user_roles(db, user, body.role_ids)
    log_service.create_log(
        db, user_id=None, username="admin",
        action="assign_roles", resource="user", resource_id=user.id,
        detail=f"分配角色给 {user.username}",
    )
    return success_response(UserOut.model_validate(user), "角色分配成功")


# ============================================================================
# 角色管理
# ============================================================================


from app.repositories import role_repository  # noqa: E402
from app.schemas.role import (  # noqa: E402
    RoleCreate,
    RoleListOut,
    RoleOut,
    RoleStatusUpdate,
    RoleUpdate,
)


@router.get("/roles")
def list_roles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    roles, total = role_repository.get_roles(
        db, page=page, page_size=page_size, keyword=keyword
    )
    data = [RoleListOut.model_validate(r) for r in roles]
    return paginated_response(data, total, page, page_size)


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(
    body: RoleCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    if role_repository.get_role_by_name(db, body.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="角色名称已存在"
        )
    role = role_repository.create_role(
        db,
        name=body.name,
        description=body.description,
        role_type=body.role_type,
        permission_ids=body.permission_ids,
    )
    log_service.create_log(
        db, user_id=None, username="admin",
        action="create", resource="role", resource_id=role.id,
        detail=f"创建角色 {role.name}",
    )
    return success_response(RoleOut.model_validate(role), "角色创建成功")


@router.get("/roles/{role_id}")
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = role_repository.get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return success_response(RoleOut.model_validate(role))


@router.put("/roles/{role_id}")
def update_role(
    role_id: int,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = role_repository.get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    role = role_repository.update_role(db, role, **body.model_dump(exclude_unset=True))
    log_service.create_log(
        db, user_id=None, username="admin",
        action="update", resource="role", resource_id=role.id,
        detail=f"修改角色 {role.name}",
    )
    return success_response(RoleOut.model_validate(role), "角色修改成功")


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = role_repository.get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    role_repository.delete_role(db, role)
    log_service.create_log(
        db, user_id=None, username="admin",
        action="delete", resource="role", resource_id=role_id,
        detail=f"删除角色 {role.name}",
    )
    return success_response(message="角色删除成功")


@router.patch("/roles/{role_id}/status")
def update_role_status(
    role_id: int,
    body: RoleStatusUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = role_repository.get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    role = role_repository.set_role_status(db, role, body.status)
    log_service.create_log(
        db, user_id=None, username="admin",
        action="status_change", resource="role", resource_id=role.id,
        detail=f"修改角色 {role.name} 状态为 {body.status}",
    )
    return success_response(RoleOut.model_validate(role), "角色状态已更新")


# ============================================================================
# 权限 & 菜单
# ============================================================================


from app.repositories import menu_repository  # noqa: E402
from app.schemas.menu import MenuTreeOut, PermissionListOut, RoleMenuUpdate  # noqa: E402


@router.get("/permissions")
def list_permissions(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    perms = menu_repository.get_all_permissions(db)
    return success_response([PermissionListOut.model_validate(p) for p in perms])


@router.get("/permissions/current")
def get_current_user_permissions(
    current_user: User = Depends(get_current_user),
):
    codes = list({perm.code for role in current_user.roles for perm in role.permissions})
    return success_response(codes)


@router.get("/menus")
def get_menu_tree(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    roots = menu_repository.get_menu_tree(db)
    return success_response([MenuTreeOut.model_validate(m) for m in roots])


@router.get("/menus/current")
def get_current_user_menus(
    current_user: User = Depends(get_current_user),
):
    menu_set = {}
    for role in current_user.roles:
        for menu in role.menus:
            menu_set[menu.id] = menu

    all_menus = list(menu_set.values())
    roots = [m for m in all_menus if m.parent_id is None]

    def build_children(parent):
        children = [m for m in all_menus if m.parent_id == parent.id]
        return {
            "id": parent.id,
            "key": parent.key,
            "name": parent.name,
            "path": parent.path,
            "icon": parent.icon,
            "parent_id": parent.parent_id,
            "sort_order": parent.sort_order,
            "children": [build_children(c) for c in sorted(children, key=lambda x: x.sort_order)],
        }

    return success_response([build_children(r) for r in sorted(roots, key=lambda x: x.sort_order)])


@router.get("/roles/{role_id}/menus")
def get_role_menus(
    role_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = role_repository.get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    menus = menu_repository.get_role_menus(db, role_id)
    data = [
        {"id": m.id, "key": m.key, "name": m.name, "path": m.path,
         "icon": m.icon, "parent_id": m.parent_id}
        for m in menus
    ]
    return success_response(data)


@router.put("/roles/{role_id}/menus")
def save_role_menus(
    role_id: int,
    body: RoleMenuUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    role = role_repository.get_role_by_id(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    role_repository.set_role_menus(db, role, body.menu_ids)
    log_service.create_log(
        db, user_id=None, username="admin",
        action="assign_menus", resource="role", resource_id=role.id,
        detail=f"分配菜单给角色 {role.name}",
    )
    return success_response(message="角色菜单保存成功")


# ============================================================================
# 日志管理
# ============================================================================

import asyncio  # noqa: E402
import json  # noqa: E402
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from fastapi import WebSocket, WebSocketDisconnect  # noqa: E402

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _format_beijing_time(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


@router.get("/logs")
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    action: str = Query(""),
    resource: str = Query(""),
    username: str = Query(""),
    start_date: str = Query(""),
    end_date: str = Query(""),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    logs, total = log_repository.get_logs(
        db,
        page=page, page_size=page_size,
        keyword=keyword, action=action, resource=resource,
        username=username, start_date=start_date, end_date=end_date,
    )
    data = [
        {
            "id": lg.id, "user_id": lg.user_id, "username": lg.username,
            "action": lg.action, "resource": lg.resource,
            "resource_id": lg.resource_id, "detail": lg.detail,
            "ip_address": lg.ip_address,
            "created_at": _format_beijing_time(lg.created_at),
        }
        for lg in logs
    ]
    return paginated_response(data, total, page, page_size)


@router.get("/logs/export")
def export_logs(
    keyword: str = Query(""),
    action: str = Query(""),
    resource: str = Query(""),
    username: str = Query(""),
    start_date: str = Query(""),
    end_date: str = Query(""),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    logs, _ = log_repository.get_logs(
        db, page=1, page_size=10000,
        keyword=keyword, action=action, resource=resource,
        username=username, start_date=start_date, end_date=end_date,
    )
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["ID", "用户名", "操作", "资源", "资源ID", "详情", "IP", "时间"])
    for lg in logs:
        writer.writerow([
            lg.id,
            lg.username,
            lg.action,
            lg.resource,
            lg.resource_id or "",
            lg.detail,
            lg.ip_address,
            _format_beijing_time(lg.created_at),
        ])

    filename = quote("system-logs.csv")
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/my-logs")
def get_my_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logs, total = log_repository.get_user_logs(
        db, current_user.id, page=page, page_size=page_size
    )
    data = [
        {
            "id": lg.id, "username": lg.username,
            "action": lg.action, "resource": lg.resource,
            "detail": lg.detail, "ip_address": lg.ip_address,
            "created_at": _format_beijing_time(lg.created_at),
        }
        for lg in logs
    ]
    return paginated_response(data, total, page, page_size)


# ============================================================================
# WebSocket - 实时日志流
# ============================================================================

@router.websocket("/logs/stream")
async def logs_stream(websocket: WebSocket):
    await websocket.accept()
    log_service.register_ws_client(websocket)
    try:
        while True:
            await websocket.receive_text()
            entry = {
                "username": "system",
                "action": "heartbeat",
                "resource": "websocket",
                "detail": "实时日志推送",
                "ip_address": "",
                "created_at": datetime.now().isoformat(),
            }
            await websocket.send_text(json.dumps(entry, ensure_ascii=False))
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        log_service.unregister_ws_client(websocket)

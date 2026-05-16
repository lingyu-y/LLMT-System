"""Idempotent development bootstrap data."""

import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
logger = logging.getLogger(__name__)

MENU_DEFINITIONS = [
    {"key": "dashboard", "name": "仪表盘", "path": "/dashboard", "icon": "Monitor", "sort_order": 1},
    {"key": "dataset", "name": "数据处理", "path": "/data-processing", "icon": "Files", "sort_order": 2},
    {"key": "training", "name": "模型训练", "path": "/model-training", "icon": "DataAnalysis", "sort_order": 3},
    {"key": "model", "name": "模型管理", "path": "/model-management", "icon": "Management", "sort_order": 4},
    {"key": "document", "name": "文档生成", "path": "/doc-generation", "icon": "Document", "sort_order": 5},
    {"key": "system", "name": "系统管理", "path": "/system", "icon": "Setting", "sort_order": 6},
    {"key": "system:user", "name": "用户管理", "path": "/system/users", "icon": "User", "parent": "system", "sort_order": 1},
    {"key": "system:role", "name": "角色管理", "path": "/system/roles", "icon": "Lock", "parent": "system", "sort_order": 2},
    {"key": "system:menu", "name": "菜单管理", "path": "/system/menus", "icon": "Menu", "parent": "system", "sort_order": 3},
    {"key": "system:log", "name": "日志管理", "path": "/system/log", "icon": "Document", "parent": "system", "sort_order": 4},
]


def _get_or_create_role(db: Session, name: str, role_type: str, description: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role is None:
        role = Role(name=name, role_type=role_type, description=description, status="active")
        db.add(role)
        db.flush()
    return role


def _ensure_menus(db: Session) -> list[Menu]:
    created: dict[str, Menu] = {}
    for definition in MENU_DEFINITIONS:
        menu = db.query(Menu).filter(Menu.key == definition["key"]).first()
        if menu is None:
            parent_key = definition.get("parent")
            parent = created.get(parent_key) if isinstance(parent_key, str) else None
            if parent is None and isinstance(parent_key, str):
                parent = db.query(Menu).filter(Menu.key == parent_key).first()
            menu = Menu(
                key=definition["key"],
                name=definition["name"],
                path=definition["path"],
                icon=definition["icon"],
                parent_id=parent.id if parent else None,
                sort_order=definition["sort_order"],
            )
            db.add(menu)
            db.flush()
        created[menu.key] = menu
    return list(created.values())


def ensure_bootstrap_data() -> None:
    """Create baseline roles, menus, and the system administrator when possible."""

    db = SessionLocal()
    try:
        admin_role = _get_or_create_role(db, "admin", "系统管理员", "拥有全部菜单和系统管理能力")
        user_role = _get_or_create_role(db, "user", "普通用户", "默认注册用户，可访问仪表盘和文档生成")

        admin = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                real_name="系统管理员",
            )
            db.add(admin)
        admin.real_name = admin.real_name or "系统管理员"
        admin.password_hash = hash_password(ADMIN_PASSWORD)
        admin.status = "active"
        admin.is_superuser = True
        admin.roles = [admin_role]

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to bootstrap admin account")
    finally:
        db.close()

    db = SessionLocal()
    try:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        user_role = db.query(Role).filter(Role.name == "user").first()
        if admin_role is None or user_role is None:
            return

        menus = _ensure_menus(db)
        admin_role.menus = menus
        user_role.menus = [menu for menu in menus if menu.key in {"dashboard", "document"}]
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to bootstrap role menus")
    finally:
        db.close()

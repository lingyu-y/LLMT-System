"""Role repository."""

from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission
from app.models.role import Role


def get_role_by_id(db: Session, role_id: int) -> Role | None:
    return db.query(Role).filter(Role.id == role_id).first()


def get_role_by_name(db: Session, name: str) -> Role | None:
    return db.query(Role).filter(Role.name == name).first()


def get_roles(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
) -> tuple[list[Role], int]:
    q = db.query(Role)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(Role.name.ilike(like) | Role.description.ilike(like))
    total = q.count()
    roles = (
        q.order_by(Role.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    )
    return roles, total


def create_role(
    db: Session,
    name: str,
    description: str | None = None,
    role_type: str | None = None,
    permission_ids: list[int] | None = None,
) -> Role:
    role = Role(name=name, description=description, role_type=role_type)
    if permission_ids:
        perms = db.query(Permission).filter(Permission.id.in_(permission_ids)).all()
        role.permissions = perms
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def update_role(db: Session, role: Role, **kwargs) -> Role:
    permission_ids = kwargs.pop("permission_ids", None)
    for key, value in kwargs.items():
        if value is not None:
            setattr(role, key, value)
    if permission_ids is not None:
        perms = db.query(Permission).filter(Permission.id.in_(permission_ids)).all()
        role.permissions = perms
    db.commit()
    db.refresh(role)
    return role


def delete_role(db: Session, role: Role) -> None:
    db.delete(role)
    db.commit()


def set_role_status(db: Session, role: Role, status: str) -> Role:
    role.status = status
    db.commit()
    db.refresh(role)
    return role


def set_role_menus(db: Session, role: Role, menu_ids: list[int]) -> Role:
    menus = db.query(Menu).filter(Menu.id.in_(menu_ids)).all() if menu_ids else []
    role.menus = menus
    db.commit()
    db.refresh(role)
    return role

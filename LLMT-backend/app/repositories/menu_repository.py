"""Menu repository."""

from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission


def get_all_permissions(db: Session) -> list[Permission]:
    return db.query(Permission).order_by(Permission.id).all()


def get_menu_tree(db: Session) -> list[Menu]:
    return (
        db.query(Menu)
        .filter(Menu.parent_id.is_(None))
        .order_by(Menu.sort_order)
        .all()
    )


def get_role_menus(db: Session, role_id: int) -> list[Menu]:
    from app.models.role import Role

    role = db.query(Role).filter(Role.id == role_id).first()
    if role is None:
        return []
    return role.menus

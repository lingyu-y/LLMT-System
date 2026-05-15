"""User repository."""

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_users(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    status: str | None = None,
) -> tuple[list[User], int]:
    q = db.query(User)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            User.username.ilike(like)
            | User.real_name.ilike(like)
            | User.email.ilike(like)
        )
    if status is not None:
        q = q.filter(User.status == status)
    total = q.count()
    users = (
        q.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    )
    return users, total


def create_user(
    db: Session,
    username: str,
    password: str,
    real_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    role_ids: list[int] | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        real_name=real_name,
        email=email,
        phone=phone,
    )
    if role_ids:
        roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
        user.roles = roles
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, **kwargs) -> User:
    password = kwargs.pop("password", None)
    if password:
        kwargs["password_hash"] = hash_password(password)
    for key, value in kwargs.items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def set_user_status(db: Session, user: User, status: str) -> User:
    user.status = status
    db.commit()
    db.refresh(user)
    return user


def set_user_roles(db: Session, user: User, role_ids: list[int]) -> User:
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all() if role_ids else []
    user.roles = roles
    db.commit()
    db.refresh(user)
    return user

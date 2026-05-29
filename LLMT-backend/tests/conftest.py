"""Shared pytest fixtures for backend tests.

The suite uses a local SQLite database and mocks external services so tests do
not require Postgres, MinIO, Redis/Celery, GPUs, or model inference services.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEST_DB = BACKEND_ROOT / "tests" / "_pytest_llmt.db"
os.environ.setdefault("POSTGRES_DATABASE_URL", f"sqlite:///{TEST_DB}")

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.dependencies.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Dataset, Menu, ModelVersion, Role, TrainingTask, User  # noqa: E402,F401


@pytest.fixture()
def db_session() -> Iterator:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def app_client(db_session) -> Iterator[TestClient]:
    def override_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _role(db, name: str, role_type: str, menus: list[Menu] | None = None) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role is None:
        role = Role(name=name, role_type=role_type, status="active")
        db.add(role)
    role.role_type = role_type
    role.status = "active"
    if menus:
        role.menus = menus
    db.commit()
    db.refresh(role)
    return role


@pytest.fixture()
def seeded_users(db_session):
    menu_specs = [
        ("dashboard", "仪表盘", "/dashboard"),
        ("datasets", "数据处理", "/datasets"),
        ("training", "模型训练", "/training"),
        ("models", "模型管理", "/models"),
        ("documents", "文档生成", "/documents"),
        ("system", "系统管理", "/system"),
    ]
    menus = []
    for key, name, path in menu_specs:
        menu = db_session.query(Menu).filter(Menu.key == key).first()
        if menu is None:
            menu = Menu(key=key, name=name, path=path)
            db_session.add(menu)
        else:
            menu.name = name
            menu.path = path
        menus.append(menu)
    db_session.commit()

    admin_role = _role(db_session, "admin", "管理员", menus)
    user_role = _role(db_session, "user", "普通", menus[:-1])

    admin = db_session.query(User).filter(User.username == "admin").first()
    if admin is None:
        admin = User(username="admin", password_hash=hash_password("admin123"))
        db_session.add(admin)
    admin.real_name = "管理员"
    admin.password_hash = hash_password("admin123")
    admin.status = "active"
    admin.is_superuser = True
    admin.roles = [admin_role]

    user = db_session.query(User).filter(User.username == "alice").first()
    if user is None:
        user = User(username="alice", password_hash=hash_password("alice123"))
        db_session.add(user)
    user.real_name = "普通用户"
    user.password_hash = hash_password("alice123")
    user.status = "active"
    user.is_superuser = False
    user.roles = [user_role]

    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(user)
    return {"admin": admin, "user": user, "menus": menus}


@pytest.fixture()
def auth_headers(seeded_users):
    def build(username: str = "alice") -> dict[str, str]:
        user = seeded_users["admin"] if username == "admin" else seeded_users["user"]
        token = create_access_token({"sub": str(user.id), "username": user.username})
        return {"Authorization": f"Bearer {token}"}

    return build


@pytest.fixture()
def completed_dataset(db_session, seeded_users) -> Dataset:
    dataset = Dataset(
        name="clean-jsonl",
        data_type="text",
        version="v1.0.0",
        source="fixture",
        storage_path="datasets/clean-jsonl",
        file_count=1,
        total_size=128,
        owner_id=seeded_users["user"].id,
        processing_status="completed",
        quality_status="passed",
        lineage_status="tracked",
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset


@pytest.fixture()
def current_model(db_session) -> ModelVersion:
    model = ModelVersion(
        model_name="LLMT GPT",
        model_code="llmt-gpt",
        version="v1.0.0",
        framework="pytorch",
        storage_path="models/llmt-gpt/v1.0.0",
        metrics_json={"loss_final": 0.21},
        hyperparams_json={"model_type": "gpt2", "batch_size": 8},
        is_current=True,
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)
    return model


@dataclass
class FakeObject:
    object_name: str
    size: int = 0
    is_dir: bool = False


class FakeMinio:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return True

    def stat_object(self, bucket: str, object_name: str):
        import hashlib

        data = self.objects[(bucket, object_name)]
        return type("Stat", (), {"etag": hashlib.md5(data).hexdigest(), "size": len(data)})()

    def put_object(self, bucket: str, object_name: str, data, length: int, *_, **__):
        self.objects[(bucket, object_name)] = data.read(length)

    def fput_object(self, bucket: str, object_name: str, file_path: str, *_, **__):
        self.objects[(bucket, object_name)] = Path(file_path).read_bytes()

    def copy_object(self, bucket: str, target_name: str, source, *_, **__):
        source_name = getattr(source, "object_name", "")
        source_bucket = getattr(source, "bucket_name", bucket)
        self.objects[(bucket, target_name)] = self.objects.get((source_bucket, source_name), b"")

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True):
        for (obj_bucket, object_name), data in self.objects.items():
            if obj_bucket == bucket and object_name.startswith(prefix):
                yield FakeObject(object_name=object_name, size=len(data))

    def get_object(self, bucket: str, object_name: str):
        return BytesIO(self.objects[(bucket, object_name)])


@pytest.fixture()
def fake_minio() -> FakeMinio:
    return FakeMinio()

"""端点 1/22 测试：GET /api/v1/system/users — 用户列表"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在导入 app 模块前设置环境变量，确保 engine 用 SQLite 创建
_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_ep1.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

# 清理上次测试残留
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)

from app.core.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.menu import Menu  # noqa: E402, F401
from app.models.permission import Permission  # noqa: E402, F401
from app.models.role import Role  # noqa: E402, F401
from app.models.system_log import SystemLog  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
from fastapi.testclient import TestClient  # noqa: E402

# 创建表
Base.metadata.create_all(bind=engine)  # type: ignore[name-defined] # noqa: F821


def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

PREFIX = "/api/v1"


def test_list_users_empty():
    """查询用户列表：创建 admin 后查询，应返回 total >= 1。"""
    db = SessionLocal()
    try:
        role = Role(name="admin", role_type="管理员")
        db.add(role)
        db.commit()

        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            is_superuser=True,
        )
        admin.roles = [role]
        db.add(admin)
        db.commit()
        db.refresh(admin)

        token = create_access_token({"sub": str(admin.id)})
        print(f"  DEBUG: admin.id={admin.id}, username={admin.username}")
    finally:
        db.close()

    client = TestClient(app)
    resp = client.get(
        f"{PREFIX}/system/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"  RESP: {resp.status_code} {resp.text[:150]}")
    assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["total"] >= 1
    assert body["data"][0]["username"] == "admin"
    print(f"  [PASS] GET /users -> total={body['total']}, page={body['page']}")


def test_list_users_requires_auth():
    """无 Token 请求应返回 401。"""
    client = TestClient(app)
    resp = client.get(f"{PREFIX}/system/users")
    assert resp.status_code == 401
    print("  [PASS] 无认证令牌返回 401")

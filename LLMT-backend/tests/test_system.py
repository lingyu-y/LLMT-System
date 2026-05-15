"""第8部分 系统管理接口 — 全部 21 端点统筹测试"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_all.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.menu import Menu  # noqa: E402, F401
from app.models.permission import Permission  # noqa: E402, F401
from app.models.role import Role  # noqa: E402, F401
from app.models.system_log import SystemLog  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401

Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

PREFIX = "/api/v1"


# ============================================================================
# 测试夹具：每个模块共享一个 session 级 admin token
# ============================================================================


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def admin_token(db: Session):
    """创建 admin 用户，返回 token。"""
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        r = Role(name="admin", role_type="管理员")
        db.add(r)
        db.commit()
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            is_superuser=True,
        )
        admin.roles = [r]
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return create_access_token({"sub": str(admin.id)})


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============================================================================
# 1. 用户管理 (7 端点)
# ============================================================================


class TestUserManagement:
    created_uid: int = 0

    def test_01_list_users_empty(self, client, admin_headers):
        """GET /users — 初始仅有 admin。"""
        resp = client.get(f"{PREFIX}/system/users", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        usernames = {u["username"] for u in body["data"]}
        assert "admin" in usernames

    def test_02_create_user(self, client, admin_headers):
        """POST /users — 创建用户。"""
        resp = client.post(
            f"{PREFIX}/system/users",
            json={"username": "sys_testuser", "real_name": "测试", "password": "pass1234"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["username"] == "sys_testuser"
        TestUserManagement.created_uid = data["id"]

    def test_03_create_duplicate(self, client, admin_headers):
        """POST /users — 重复名 409。"""
        resp = client.post(
            f"{PREFIX}/system/users",
            json={"username": "sys_testuser", "password": "pass1234"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_04_get_user(self, client, admin_headers):
        """GET /users/{id} — 用户详情。"""
        uid = TestUserManagement.created_uid
        resp = client.get(f"{PREFIX}/system/users/{uid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "sys_testuser"

    def test_05_update_user(self, client, admin_headers):
        """PUT /users/{id} — 修改用户。"""
        uid = TestUserManagement.created_uid
        resp = client.put(
            f"{PREFIX}/system/users/{uid}",
            json={"real_name": "修改后"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["real_name"] == "修改后"

    def test_06_disable_user(self, client, admin_headers):
        """PATCH /users/{id}/status — 锁定用户。"""
        uid = TestUserManagement.created_uid
        resp = client.patch(
            f"{PREFIX}/system/users/{uid}/status",
            json={"status": "locked"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "locked"

    def test_07_assign_roles(self, client, admin_headers, db):
        """PUT /users/{id}/roles — 分配角色。"""
        uid = TestUserManagement.created_uid
        # 确保有可分配的角色
        r = db.query(Role).filter(Role.name == "admin").first()
        resp = client.put(
            f"{PREFIX}/system/users/{uid}/roles",
            json={"role_ids": [r.id]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]["roles"]) == 1

    def test_08_delete_user(self, client, admin_headers, db):
        """DELETE /users/{id} — 删除用户。"""
        # 创建临时用户用于删除
        u = User(username="todel", password_hash=hash_password("x"))
        db.add(u)
        db.commit()
        db.refresh(u)
        uid = u.id

        resp = client.delete(f"{PREFIX}/system/users/{uid}", headers=admin_headers)
        assert resp.status_code == 200
        assert db.query(User).filter(User.id == uid).first() is None

    def test_09_unauthorized(self, client):
        """无 Token 应返回 401。"""
        assert client.get(f"{PREFIX}/system/users").status_code == 401


# ============================================================================
# 2. 角色管理 (6 端点)
# ============================================================================


class TestRoleManagement:
    created_rid: int = 0

    def test_10_list_roles(self, client, admin_headers):
        """GET /roles — 角色列表。"""
        resp = client.get(f"{PREFIX}/system/roles", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_11_create_role(self, client, admin_headers):
        """POST /roles — 创建角色。"""
        resp = client.post(
            f"{PREFIX}/system/roles",
            json={"name": "operator", "description": "运维", "role_type": "普通"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        TestRoleManagement.created_rid = resp.json()["data"]["id"]

    def test_12_create_duplicate(self, client, admin_headers):
        """POST /roles — 重复名 409。"""
        resp = client.post(
            f"{PREFIX}/system/roles",
            json={"name": "operator"},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_13_get_role(self, client, admin_headers):
        """GET /roles/{id} — 角色详情。"""
        rid = TestRoleManagement.created_rid
        resp = client.get(f"{PREFIX}/system/roles/{rid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "operator"

    def test_14_update_role(self, client, admin_headers):
        """PUT /roles/{id} — 修改角色。"""
        rid = TestRoleManagement.created_rid
        resp = client.put(
            f"{PREFIX}/system/roles/{rid}",
            json={"description": "新描述"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["description"] == "新描述"

    def test_15_disable_role(self, client, admin_headers):
        """PATCH /roles/{id}/status — 禁用角色。"""
        rid = TestRoleManagement.created_rid
        resp = client.patch(
            f"{PREFIX}/system/roles/{rid}/status",
            json={"status": "disabled"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "disabled"

    def test_16_delete_role(self, client, admin_headers, db):
        """DELETE /roles/{id} — 删除角色。"""
        r = Role(name="todel_role")
        db.add(r)
        db.commit()
        db.refresh(r)
        rid = r.id
        resp = client.delete(f"{PREFIX}/system/roles/{rid}", headers=admin_headers)
        assert resp.status_code == 200
        assert db.query(Role).filter(Role.id == rid).first() is None


# ============================================================================
# 3. 权限 & 菜单 (4 端点)
# ============================================================================


class TestPermsAndMenus:

    def test_17_list_permissions(self, client, admin_headers, db):
        """GET /permissions — 权限列表。"""
        for c in ["user:read", "role:read"]:
            if not db.query(Permission).filter(Permission.code == c).first():
                db.add(Permission(code=c, name=c, module="sys"))
        db.commit()

        resp = client.get(f"{PREFIX}/system/permissions", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    def test_18_menu_tree(self, client, admin_headers, db):
        """GET /menus — 菜单树。"""
        if not db.query(Menu).filter(Menu.key == "dash").first():
            root = Menu(key="dash", name="仪表盘", path="/dash", icon="Monitor", sort_order=1)
            db.add(root)
            db.commit()
            db.refresh(root)
            child = Menu(key="data", name="数据", path="/data", icon="Doc", parent_id=root.id, sort_order=0)
            db.add(child)
            db.commit()

        resp = client.get(f"{PREFIX}/system/menus", headers=admin_headers)
        assert resp.status_code == 200
        roots = resp.json()["data"]
        assert len(roots) >= 1
        assert len(roots[0]["children"]) >= 1

    def test_19_get_role_menus(self, client, admin_headers, db):
        """GET /roles/{id}/menus — 查询角色菜单。"""
        role = db.query(Role).filter(Role.name == "admin").first()
        menus = db.query(Menu).all()
        role.menus = menus
        db.commit()

        resp = client.get(f"{PREFIX}/system/roles/{role.id}/menus", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == len(menus)

    def test_20_save_role_menus(self, client, admin_headers, db):
        """PUT /roles/{id}/menus — 保存角色菜单。"""
        r = Role(name="menu_role")
        db.add(r)
        db.commit()
        db.refresh(r)
        mids = [m.id for m in db.query(Menu).limit(2).all()]

        resp = client.put(
            f"{PREFIX}/system/roles/{r.id}/menus",
            json={"menu_ids": mids},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        db.refresh(r)
        assert len(r.menus) == len(mids)


# ============================================================================
# 4. 日志管理 (4 端点)
# ============================================================================


class TestLogManagement:

    def test_21_list_logs(self, client, admin_headers, db):
        """GET /logs — 日志列表。"""
        for a in ["create", "update"]:
            db.add(SystemLog(user_id=1, username="admin", action=a, resource="user"))
        db.commit()

        resp = client.get(f"{PREFIX}/system/logs", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

        resp2 = client.get(f"{PREFIX}/system/logs?action=create", headers=admin_headers)
        assert resp2.json()["total"] >= 1

    def test_22_export_logs(self, client, admin_headers):
        """GET /logs/export — 导出日志。"""
        resp = client.get(f"{PREFIX}/system/logs/export", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "header" in data
        assert data["total"] >= 1

    def test_23_my_logs(self, client, admin_headers, db):
        """GET /my-logs — 当前用户日志。"""
        resp = client.get(f"{PREFIX}/system/my-logs", headers=admin_headers)
        assert resp.status_code == 200
        for entry in resp.json()["data"]:
            assert entry["username"] == "admin"

    def test_24_websocket_stream(self, client):
        """WS /logs/stream — WebSocket 实时流。"""
        with client.websocket_connect(f"{PREFIX}/system/logs/stream") as ws:
            ws.send_text("ping")
            msg = json.loads(ws.receive_text())
            assert "username" in msg
            assert "created_at" in msg

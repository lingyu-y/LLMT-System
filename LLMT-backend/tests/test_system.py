"""第八部分 系统管理接口 — 24 端点测试"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_sys.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB): os.remove(_TEST_DB)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.menu import Menu  # noqa: F401
from app.models.permission import Permission  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.system_log import SystemLog  # noqa: F401
from app.models.user import User  # noqa: F401

Base.metadata.create_all(bind=engine)

def _ovr():
    db = SessionLocal()
    try: yield db
    finally: db.close()
app.dependency_overrides[get_db] = _ovr
PREFIX = "/api/v1"

@pytest.fixture(scope="module")
def client(): return TestClient(app)
@pytest.fixture(scope="module")
def db():
    s = SessionLocal(); yield s; s.rollback(); s.close()
@pytest.fixture(scope="module")
def admin_headers(db: Session):
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        r = Role(name="admin", role_type="管理员"); db.add(r); db.commit()
        admin = User(username="admin", password_hash=hash_password("admin123"), is_superuser=True)
        admin.roles = [r]; db.add(admin); db.commit(); db.refresh(admin)
    token = create_access_token({"sub": str(admin.id)})
    return {"Authorization": f"Bearer {token}"}

class TestUsers:
    uid = 0
    def test_01_list(self, client, admin_headers):
        resp = client.get(f"{PREFIX}/system/users", headers=admin_headers)
        assert resp.status_code == 200 and resp.json()["total"] >= 1
    def test_02_create(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/system/users", json={"username": "sys_u", "password": "pass1234"}, headers=admin_headers)
        assert resp.status_code == 201; TestUsers.uid = resp.json()["data"]["id"]
    def test_03_duplicate(self, client, admin_headers):
        assert client.post(f"{PREFIX}/system/users", json={"username": "sys_u", "password": "pass1234"}, headers=admin_headers).status_code == 409
    def test_04_get(self, client, admin_headers):
        assert client.get(f"{PREFIX}/system/users/{TestUsers.uid}", headers=admin_headers).status_code == 200
    def test_05_update(self, client, admin_headers):
        resp = client.put(f"{PREFIX}/system/users/{TestUsers.uid}", json={"real_name": "改"}, headers=admin_headers)
        assert resp.status_code == 200 and resp.json()["data"]["real_name"] == "改"
    def test_06_disable(self, client, admin_headers):
        resp = client.patch(f"{PREFIX}/system/users/{TestUsers.uid}/status", json={"status": "locked"}, headers=admin_headers)
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "locked"
    def test_07_roles(self, client, admin_headers, db):
        r = db.query(Role).filter(Role.name == "admin").first()
        assert client.put(f"{PREFIX}/system/users/{TestUsers.uid}/roles", json={"role_ids": [r.id]}, headers=admin_headers).status_code == 200
    def test_08_delete(self, client, admin_headers, db):
        u = User(username="td", password_hash=hash_password("x")); db.add(u); db.commit(); db.refresh(u)
        assert client.delete(f"{PREFIX}/system/users/{u.id}", headers=admin_headers).status_code == 200
    def test_09_unauth(self, client):
        assert client.get(f"{PREFIX}/system/users").status_code == 401

class TestRoles:
    rid = 0
    def test_10_list(self, client, admin_headers):
        assert client.get(f"{PREFIX}/system/roles", headers=admin_headers).status_code == 200
    def test_11_create(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/system/roles", json={"name": "op"}, headers=admin_headers)
        assert resp.status_code == 201; TestRoles.rid = resp.json()["data"]["id"]
    def test_12_duplicate(self, client, admin_headers):
        assert client.post(f"{PREFIX}/system/roles", json={"name": "op"}, headers=admin_headers).status_code == 409
    def test_13_get(self, client, admin_headers):
        assert client.get(f"{PREFIX}/system/roles/{TestRoles.rid}", headers=admin_headers).status_code == 200
    def test_14_update(self, client, admin_headers):
        assert client.put(f"{PREFIX}/system/roles/{TestRoles.rid}", json={"description": "新"}, headers=admin_headers).status_code == 200
    def test_15_disable(self, client, admin_headers):
        resp = client.patch(f"{PREFIX}/system/roles/{TestRoles.rid}/status", json={"status": "disabled"}, headers=admin_headers)
        assert resp.status_code == 200
    def test_16_delete(self, client, admin_headers, db):
        r = Role(name="tdr"); db.add(r); db.commit(); db.refresh(r)
        assert client.delete(f"{PREFIX}/system/roles/{r.id}", headers=admin_headers).status_code == 200

class TestPermsMenus:
    def test_17_perms(self, client, admin_headers, db):
        for c in ["a:1", "b:2"]:
            if not db.query(Permission).filter(Permission.code == c).first(): db.add(Permission(code=c, name=c, module="s"))
        db.commit()
        assert client.get(f"{PREFIX}/system/permissions", headers=admin_headers).status_code == 200
    def test_18_menu_tree(self, client, admin_headers, db):
        if not db.query(Menu).filter(Menu.key == "d").first():
            r = Menu(key="d", name="D", path="/d", icon="M", sort_order=1); db.add(r); db.commit(); db.refresh(r)
            db.add(Menu(key="c", name="C", path="/c", icon="D", parent_id=r.id, sort_order=0)); db.commit()
        assert client.get(f"{PREFIX}/system/menus", headers=admin_headers).status_code == 200
    def test_19_role_menus_get(self, client, admin_headers, db):
        role = db.query(Role).filter(Role.name == "admin").first()
        role.menus = db.query(Menu).all(); db.commit()
        assert client.get(f"{PREFIX}/system/roles/{role.id}/menus", headers=admin_headers).status_code == 200
    def test_20_role_menus_save(self, client, admin_headers, db):
        r = Role(name="mr"); db.add(r); db.commit(); db.refresh(r)
        mids = [m.id for m in db.query(Menu).limit(2)]
        assert client.put(f"{PREFIX}/system/roles/{r.id}/menus", json={"menu_ids": mids}, headers=admin_headers).status_code == 200

class TestLogs:
    def test_21_list(self, client, admin_headers, db):
        for a in ["c", "u"]: db.add(SystemLog(user_id=1, username="a", action=a, resource="x"))
        db.commit()
        assert client.get(f"{PREFIX}/system/logs", headers=admin_headers).status_code == 200
    def test_22_export(self, client, admin_headers):
        assert client.get(f"{PREFIX}/system/logs/export", headers=admin_headers).status_code == 200
    def test_23_my_logs(self, client, admin_headers):
        assert client.get(f"{PREFIX}/system/my-logs", headers=admin_headers).status_code == 200
    def test_24_ws(self, client):
        with client.websocket_connect(f"{PREFIX}/system/logs/stream") as ws:
            ws.send_text("p"); msg = json.loads(ws.receive_text())
            assert "created_at" in msg

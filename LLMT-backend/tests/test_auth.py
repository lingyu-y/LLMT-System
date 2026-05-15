"""第一部分 认证接口 — 6 端点测试"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_auth.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB): os.remove(_TEST_DB)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.role import Role  # noqa: F401
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
def setup_user(db: Session):
    u = db.query(User).filter(User.username == "testuser").first()
    if u is None:
        r = Role(name="user", role_type="普通"); db.add(r); db.commit()
        u = User(username="testuser", real_name="测试", password_hash=hash_password("test1234"), status="active")
        u.roles = [r]; db.add(u); db.commit(); db.refresh(u)
    return u

class TestAuth:
    token = ""
    def test_01_login_ok(self, client, setup_user):
        resp = client.post(f"{PREFIX}/auth/login", json={"username": "testuser", "password": "test1234"})
        assert resp.status_code == 200; TestAuth.token = resp.json()["token"]
    def test_02_login_bad(self, client, setup_user):
        assert client.post(f"{PREFIX}/auth/login", json={"username": "testuser", "password": "wrong"}).status_code == 401
    def test_03_me(self, client, setup_user):
        resp = client.get(f"{PREFIX}/auth/me", headers={"Authorization": f"Bearer {TestAuth.token}"})
        assert resp.status_code == 200
    def test_04_refresh(self, client, setup_user):
        assert client.post(f"{PREFIX}/auth/refresh", headers={"Authorization": f"Bearer {TestAuth.token}"}).status_code == 200
    def test_05_demo(self, client, setup_user):
        assert client.get(f"{PREFIX}/auth/demo-accounts").status_code == 200
    def test_06_logout(self, client, setup_user):
        assert client.post(f"{PREFIX}/auth/logout", headers={"Authorization": f"Bearer {TestAuth.token}"}).status_code == 200

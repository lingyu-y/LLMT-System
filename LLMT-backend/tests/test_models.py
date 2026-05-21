"""第五部分 模型管理与安全接口 — 15 端点测试"""

import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_mod.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB): os.remove(_TEST_DB)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.model_version import ModelVersion  # noqa: F401
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
def admin_headers(db: Session):
    u = db.query(User).filter(User.username == "admin").first()
    if u is None:
        r = Role(name="admin"); db.add(r); db.commit()
        u = User(username="admin", password_hash=hash_password("x"), is_superuser=True)
        u.roles = [r]; db.add(u); db.commit(); db.refresh(u)
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


def _seed_model(db: Session, code="test-model", ver="v1.0"):
    m = db.query(ModelVersion).filter(ModelVersion.model_code == code, ModelVersion.version == ver).first()
    if m is None:
        m = ModelVersion(model_name="测试模型", model_code=code, version=ver, storage_path=f"m/{code}/{ver}",
                         is_current=True, metrics_json={}, hyperparams_json={})
        db.add(m); db.commit(); db.refresh(m)
    return m


class TestModelCRUD:
    def test_01_list(self, client, admin_headers, db):
        _seed_model(db)
        resp = client.get(f"{PREFIX}/models", headers=admin_headers)
        assert resp.status_code == 200 and resp.json()["total"] >= 1

    def test_02_create(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/models", json={"model_name": "新建", "model_code": "new-m", "version": "v1"}, headers=admin_headers)
        assert resp.status_code == 201 and resp.json()["data"]["model_code"] == "new-m"

    def test_03_create_duplicate(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/models", json={"model_name": "D", "model_code": "new-m", "version": "v1"}, headers=admin_headers)
        assert resp.status_code == 409

    def test_04_get(self, client, admin_headers, db):
        m = _seed_model(db, "get-test", "v1")
        resp = client.get(f"{PREFIX}/models/{m.model_code}", headers=admin_headers)
        assert resp.status_code == 200

    def test_05_versions(self, client, admin_headers, db):
        m = _seed_model(db, "ver-test", "v1")
        resp = client.get(f"{PREFIX}/models/{m.model_code}/versions", headers=admin_headers)
        assert resp.status_code == 200 and len(resp.json()["data"]) >= 1

    def test_06_create_version(self, client, admin_headers, db):
        _seed_model(db, "ver2-test", "v1")
        resp = client.post(f"{PREFIX}/models/ver2-test/versions", json={"version": "v2"}, headers=admin_headers)
        assert resp.status_code == 201

    def test_07_version_detail(self, client, admin_headers, db):
        m = _seed_model(db, "det-test", "v1")
        resp = client.get(f"{PREFIX}/models/{m.model_code}/versions/{m.version}", headers=admin_headers)
        assert resp.status_code == 200

    def test_08_compare(self, client, admin_headers, db):
        _seed_model(db, "cmp-test", "v1")
        db.add(ModelVersion(model_name="C", model_code="cmp-test", version="v2", storage_path="m/c/v2",
                            is_current=False, metrics_json={}, hyperparams_json={}))
        db.commit()
        resp = client.get(f"{PREFIX}/models/cmp-test/versions/compare?v1=v1&v2=v2", headers=admin_headers)
        assert resp.status_code == 200


class TestModelSecurity:
    def test_09_scan(self, client, admin_headers, db):
        m = _seed_model(db, "scan-test", "v1")
        resp = client.post(f"{PREFIX}/models/{m.model_code}/security/scan", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert "checksum" in data

    def test_10_reports(self, client, admin_headers, db):
        m = _seed_model(db, "rep-test", "v1")
        resp = client.get(f"{PREFIX}/models/{m.model_code}/security/reports", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1


class TestModelRateLimit:
    def test_11_get_limit(self, client, admin_headers, db):
        m = _seed_model(db, "rl-test", "v1")
        resp = client.get(f"{PREFIX}/models/{m.model_code}/rate-limit", headers=admin_headers)
        assert resp.status_code == 200
        assert "limits" in resp.json()["data"]

    def test_12_update_limit(self, client, admin_headers, db):
        m = _seed_model(db, "rl2-test", "v1")
        resp = client.put(f"{PREFIX}/models/{m.model_code}/rate-limit", json={"requests_per_minute": 50}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["limits"]["requests_per_minute"] == 50

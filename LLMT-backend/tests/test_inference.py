"""第六部分 模型推理接口 — 6 端点测试"""

import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_inf.db")
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
def auth_headers(db: Session):
    u = db.query(User).filter(User.username == "admin").first()
    if u is None:
        r = Role(name="admin"); db.add(r); db.commit()
        u = User(username="admin", password_hash=hash_password("x"), is_superuser=True)
        u.roles = [r]; db.add(u); db.commit(); db.refresh(u)
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


class TestModels:
    def test_01_list_models(self, client, auth_headers, db):
        if not db.query(ModelVersion).filter(ModelVersion.model_code == "test-model").first():
            db.add(ModelVersion(model_name="测试模型", model_code="test-model", version="v1.0",
                                storage_path="/m", is_current=True, metrics_json={}, hyperparams_json={}))
            db.commit()
        resp = client.get(f"{PREFIX}/inference/models", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

    def test_02_models_empty(self, client, auth_headers):
        resp = client.get(f"{PREFIX}/inference/models", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


class TestPredict:
    def test_03_predict_not_found(self, client, auth_headers):
        resp = client.post(f"{PREFIX}/inference/models/nonexist/predict",
                           json={"input": "test"}, headers=auth_headers)
        assert resp.status_code == 404

    def test_04_predict_ok(self, client, auth_headers, db):
        if not db.query(ModelVersion).filter(ModelVersion.model_code == "pred-model").first():
            db.add(ModelVersion(model_name="预测", model_code="pred-model", version="v1",
                                storage_path="/m", is_current=True, metrics_json={}, hyperparams_json={}))
            db.commit()
        resp = client.post(f"{PREFIX}/inference/models/pred-model/predict",
                           json={"input": "你好", "parameters": {}}, headers=auth_headers)
        assert resp.status_code == 200
        assert "output" in resp.json()["data"]


class TestAsyncJobs:
    job_id = ""

    def test_05_create_job(self, client, auth_headers):
        resp = client.post(f"{PREFIX}/inference/jobs",
                           json={"model_code": "pred-model", "input": "异步测试"}, headers=auth_headers)
        assert resp.status_code == 201
        TestAsyncJobs.job_id = resp.json()["data"]["job_id"]

    def test_06_get_job(self, client, auth_headers):
        resp = client.get(f"{PREFIX}/inference/jobs/{TestAsyncJobs.job_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "queued"

    def test_07_cancel_job(self, client, auth_headers):
        resp = client.post(f"{PREFIX}/inference/jobs/{TestAsyncJobs.job_id}/cancel", headers=auth_headers)
        assert resp.status_code == 200

    def test_08_get_job_not_found(self, client, auth_headers):
        assert client.get(f"{PREFIX}/inference/jobs/nonexist", headers=auth_headers).status_code == 404


class TestUsage:
    def test_09_usage(self, client, auth_headers):
        resp = client.get(f"{PREFIX}/inference/usage", headers=auth_headers)
        assert resp.status_code == 200
        assert "total_calls" in resp.json()["data"][0]

    def test_10_usage_filter(self, client, auth_headers):
        resp = client.get(f"{PREFIX}/inference/usage?model_code=pred-model", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

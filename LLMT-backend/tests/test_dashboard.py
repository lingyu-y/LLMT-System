"""第二部分 仪表盘接口 — 逐端点测试"""

import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_dash.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB): os.remove(_TEST_DB)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.role import Role  # noqa: F401
from app.models.system_log import SystemLog  # noqa: F401
from app.models.training_task import TrainingTask  # noqa: F401
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


class TestSummary:
    def test_01_summary(self, client, auth_headers):
        resp = client.get(f"{PREFIX}/dashboard/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "gpu_memory_used" in data
        assert "running_tasks" in data

class TestMetrics:
    def test_02_metrics(self, client, auth_headers):
        resp = client.get(f"{PREFIX}/dashboard/metrics", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "loss" in data and "gpu_utilization" in data and "latency" in data

class TestDashboardTasks:
    def test_03_training_tasks(self, client, auth_headers, db):
        if not db.query(TrainingTask).filter(TrainingTask.task_code == "test").first():
            t = TrainingTask(task_name="测试任务", task_code="test", status="running",
                             config_json={}, current_epoch=5, current_step=1000, max_epoch=10,
                             dataset_id=1, creator_id=1)
            db.add(t); db.commit()
        resp = client.get(f"{PREFIX}/dashboard/training-tasks", headers=auth_headers)
        assert resp.status_code == 200

class TestActivities:
    def test_04_activities(self, client, auth_headers, db):
        if db.query(SystemLog).count() == 0:
            db.add(SystemLog(user_id=1, username="admin", action="login", resource="auth"))
            db.commit()
        resp = client.get(f"{PREFIX}/dashboard/activities?limit=5", headers=auth_headers)
        assert resp.status_code == 200

class TestAlerts:
    def test_05_alerts(self, client, auth_headers, db):
        if db.query(SystemLog).count() == 0:
            db.add(SystemLog(user_id=1, username="admin", action="login", resource="auth"))
            db.commit()
        resp = client.get(f"{PREFIX}/dashboard/alerts?limit=5", headers=auth_headers)
        assert resp.status_code == 200

class TestStream:
    def test_06_stream(self, client):
        with client.websocket_connect(f"{PREFIX}/dashboard/stream") as ws:
            ws.send_text("ping")
            msg = ws.receive_text()
            import json
            body = json.loads(msg)
            assert "summary" in body

"""第三部分 数据处理接口 — 19 端点测试"""
import json, os, sys, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_ds.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB): os.remove(_TEST_DB)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.dataset import Dataset  # noqa: F401
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
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        r = Role(name="admin", role_type="管理员"); db.add(r); db.commit()
        admin = User(username="admin", password_hash=hash_password("admin123"), is_superuser=True)
        admin.roles = [r]; db.add(admin); db.commit(); db.refresh(admin)
    return {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}

class TestCRUD:
    did = 0
    def test_01_stats(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets/stats", headers=admin_headers).status_code == 200
    def test_02_create(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/datasets", json={"name": "测试", "data_type": "text"}, headers=admin_headers)
        assert resp.status_code == 201; TestCRUD.did = resp.json()["data"]["id"]
    def test_03_list(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets", headers=admin_headers).status_code == 200
    def test_04_filter(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets?data_type=text", headers=admin_headers).status_code == 200
    def test_05_get(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets/{TestCRUD.did}", headers=admin_headers).status_code == 200
    def test_06_update(self, client, admin_headers):
        resp = client.put(f"{PREFIX}/datasets/{TestCRUD.did}", json={"name": "已改"}, headers=admin_headers)
        assert resp.status_code == 200 and resp.json()["data"]["name"] == "已改"
    def test_07_delete(self, client, admin_headers, db):
        ds = Dataset(name="td", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.delete(f"{PREFIX}/datasets/{ds.id}", headers=admin_headers).status_code == 200
    def test_08_stats2(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets/stats", headers=admin_headers).status_code == 200

class TestUpload:
    def test_09_upload(self, client, admin_headers, db):
        ds = Dataset(name="up", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        resp = client.post(f"{PREFIX}/datasets/upload?dataset_id={ds.id}", files={"file": ("t.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")}, headers=admin_headers)
        assert resp.status_code == 200
    def test_10_resume(self, client, admin_headers):
        assert client.post(f"{PREFIX}/datasets/upload/U-001/resume", headers=admin_headers).status_code == 200
    def test_11_import(self, client, admin_headers):
        resp = client.post(f"{PREFIX}/datasets/import/external", json={"source": "mysql", "name": "外部", "data_type": "tabular"}, headers=admin_headers)
        assert resp.status_code == 200

class TestProcessing:
    def test_12_preprocess(self, client, admin_headers, db):
        ds = Dataset(name="pp", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.post(f"{PREFIX}/datasets/{ds.id}/preprocess", headers=admin_headers).status_code == 200
    def test_13_list_jobs(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets/processing-jobs", headers=admin_headers).status_code == 200
    def test_14_get_job(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets/processing-jobs/JOB-0001", headers=admin_headers).status_code == 200

class TestQuality:
    def test_15_report(self, client, admin_headers, db):
        ds = Dataset(name="qr", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.get(f"{PREFIX}/datasets/{ds.id}/quality", headers=admin_headers).status_code == 200
    def test_16_check(self, client, admin_headers, db):
        ds = Dataset(name="qc", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.post(f"{PREFIX}/datasets/{ds.id}/quality/check", headers=admin_headers).status_code == 200
    def test_17_repair(self, client, admin_headers, db):
        ds = Dataset(name="qp", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.post(f"{PREFIX}/datasets/{ds.id}/quality/repair", headers=admin_headers).status_code == 200
    def test_18_lineage(self, client, admin_headers, db):
        ds = Dataset(name="ln", data_type="text", storage_path="/t", source="kafka", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.get(f"{PREFIX}/datasets/{ds.id}/lineage", headers=admin_headers).status_code == 200
    def test_19_impact(self, client, admin_headers, db):
        ds = Dataset(name="im", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.get(f"{PREFIX}/datasets/{ds.id}/lineage/impact", headers=admin_headers).status_code == 200

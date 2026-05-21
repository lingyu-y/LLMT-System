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
from app.models.model_version import ModelVersion  # noqa: F401
from app.models.role import Role  # noqa: F401
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
        assert resp.status_code in (200, 400)  # 400 = MinIO unavailable in test
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert "checksum_verified" in data

    def test_10_upload_unsupported_format(self, client, admin_headers, db):
        ds = Dataset(name="up2", data_type="text", storage_path="/t2", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        resp = client.post(f"{PREFIX}/datasets/upload?dataset_id={ds.id}", files={"file": ("x.png", io.BytesIO(b"fake-png"), "image/png")}, headers=admin_headers)
        assert resp.status_code == 400  # format blocked

    def test_11_batch_upload(self, client, admin_headers, db):
        ds = Dataset(name="batch", data_type="text", storage_path="/tb", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        resp = client.post(f"{PREFIX}/datasets/upload/batch?dataset_id={ds.id}",
            files=[("files", ("a.txt", io.BytesIO(b"hello"), "text/plain")),
                   ("files", ("b.csv", io.BytesIO(b"x,y\n1,2"), "text/csv"))],
            headers=admin_headers)
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert data["total"] == 2

    def test_12_batch_too_many(self, client, admin_headers, db):
        ds = Dataset(name="toomany", data_type="text", storage_path="/tx", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        too_many = [("files", (f"f{i}.txt", io.BytesIO(b"x"), "text/plain")) for i in range(11)]
        resp = client.post(f"{PREFIX}/datasets/upload/batch?dataset_id={ds.id}", files=too_many, headers=admin_headers)
        assert resp.status_code == 400

    def test_13_resume_not_found(self, client, admin_headers):
        assert client.post(f"{PREFIX}/datasets/upload/no-such-uuid/resume", headers=admin_headers).status_code == 404

    def test_14_resume_ok(self, client, admin_headers):
        # Register a fake upload session then resume
        from app.services.dataset_service import save_resume_state
        save_resume_state("UPLOAD-DEMO", "data.csv", 1024000, 512000)
        resp = client.post(f"{PREFIX}/datasets/upload/UPLOAD-DEMO/resume", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_size"] == 1024000 and data["offset"] == 512000
    def test_15_import(self, client, admin_headers):
        import tempfile
        tmp = tempfile.mkdtemp()
        # 创建示例数据文件
        with open(f"{tmp}/sample.csv", "w") as f:
            f.write("col1,col2\n1,2\n3,4")
        resp = client.post(f"{PREFIX}/datasets/import/external", json={
            "source_type": "filesystem", "source_path": tmp,
            "name": "外部导入", "data_type": "tabular"
        }, headers=admin_headers)
        # MinIO 测试环境可能不可用；接受 200(成功) 或 400(MinIO 不可达)
        assert resp.status_code in (200, 400)

class TestProcessing:
    def test_16_preprocess(self, client, admin_headers, db):
        ds = Dataset(name="pp", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.post(f"{PREFIX}/datasets/{ds.id}/preprocess", headers=admin_headers).status_code == 200
    def test_17_list_jobs(self, client, admin_headers):
        assert client.get(f"{PREFIX}/datasets/processing-jobs", headers=admin_headers).status_code == 200
    def test_18_get_job(self, client, admin_headers):
        # Get the first job from the list and fetch it by its actual ID
        list_resp = client.get(f"{PREFIX}/datasets/processing-jobs", headers=admin_headers)
        jobs = list_resp.json()["data"]
        if jobs:
            job_id = jobs[0]["job_id"]
            assert client.get(f"{PREFIX}/datasets/processing-jobs/{job_id}", headers=admin_headers).status_code == 200

class TestQuality:
    def test_19_report(self, client, admin_headers, db):
        ds = Dataset(name="qr", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.get(f"{PREFIX}/datasets/{ds.id}/quality", headers=admin_headers).status_code == 200
    def test_20_check(self, client, admin_headers, db):
        ds = Dataset(name="qc", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.post(f"{PREFIX}/datasets/{ds.id}/quality/check", headers=admin_headers).status_code == 200
    def test_21_repair(self, client, admin_headers, db):
        ds = Dataset(name="qp", data_type="text", storage_path="/t", owner_id=1); db.add(ds); db.commit(); db.refresh(ds)
        assert client.post(f"{PREFIX}/datasets/{ds.id}/quality/repair", headers=admin_headers).status_code == 200
    def test_22_lineage(self, client, admin_headers, db):
        ds = Dataset(name="ln", data_type="text", storage_path="/t", source="kafka",
                     owner_id=1, file_count=100, quality_status="passed")
        db.add(ds); db.commit(); db.refresh(ds)
        # Build dependency chain: dataset → task → model
        u = db.query(User).first()
        t = TrainingTask(task_name="血缘任务", task_code="LN-TASK99", status="running",
                         config_json={}, current_epoch=3, current_step=500, max_epoch=10,
                         dataset_id=ds.id, creator_id=u.id if u else 1)
        db.add(t); db.commit(); db.refresh(t)
        m = ModelVersion(model_name="血缘模型", model_code="ln-model", version="v1",
                         storage_path="m/ln/v1", task_id=t.id, is_current=True,
                         metrics_json={"accuracy": 0.9}, hyperparams_json={},
                         dataset_version=ds.version)
        db.add(m); db.commit()
        resp = client.get(f"{PREFIX}/datasets/{ds.id}/lineage", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # R1: 来源记录（上传者、时间、原始位置）
        assert data["origin"]["uploaded_by"] is not None
        assert data["origin"]["uploaded_at"] is not None
        assert data["origin"]["original_source"] is not None
        # R2: 转换过程（规则、时间、版本）
        assert len(data["transformations"]) >= 1
        for tx in data["transformations"]:
            assert "rule" in tx and "timestamp" in tx
        # R3: 下游使用（训练任务ID、时间、结果）
        assert len(data["downstream"]) >= 2  # task + model
        task_entry = [d for d in data["downstream"] if d["type"] == "training_task"][0]
        assert "task_id" in task_entry
        assert "status" in task_entry
        assert "started_at" in task_entry

    def test_23_impact(self, client, admin_headers, db):
        ds = Dataset(name="im", data_type="text", storage_path="/t", source="mysql", owner_id=1)
        db.add(ds); db.commit(); db.refresh(ds)
        t = TrainingTask(task_name="影响任务", task_code="IM-TASK", status="completed",
                         config_json={}, current_epoch=5, current_step=1000, max_epoch=10,
                         dataset_id=ds.id, creator_id=1)
        db.add(t); db.commit(); db.refresh(t)
        m = ModelVersion(model_name="影响模型", model_code="im-model", version="v1",
                         storage_path="m/im/v1", task_id=t.id, is_current=True,
                         metrics_json={}, hyperparams_json={}, dataset_version=ds.version)
        db.add(m); db.commit()
        resp = client.get(f"{PREFIX}/datasets/{ds.id}/lineage/impact", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["affected_tasks"]) >= 1
        assert len(data["affected_models"]) >= 1

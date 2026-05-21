"""第七部分 文档生成接口 — 11 端点 + 越权测试"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_doc.db")
os.environ["POSTGRES_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.role import Role  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401

Base.metadata.create_all(bind=engine)


def _ovr():
    db = SessionLocal()
    try: yield db
    finally: db.close()


app.dependency_overrides[get_db] = _ovr
PREFIX = "/api/v1"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def db():
    s = SessionLocal(); yield s; s.rollback(); s.close()


def _make_user(db: Session, username: str) -> str:
    u = db.query(User).filter(User.username == username).first()
    if u is None:
        u = User(username=username, password_hash=hash_password("pass1234"), status="active")
        db.add(u); db.commit(); db.refresh(u)
    return create_access_token({"sub": str(u.id)})


@pytest.fixture(scope="module")
def user_a(db: Session):
    return {"Authorization": f"Bearer {_make_user(db, 'author_a')}"}


@pytest.fixture(scope="module")
def user_b(db: Session):
    return {"Authorization": f"Bearer {_make_user(db, 'author_b')}"}


class TestDocumentModels:
    def test_01_list_models(self, client, user_a):
        resp = client.get(f"{PREFIX}/documents/models", headers=user_a)
        assert resp.status_code == 200 and len(resp.json()["data"]) == 3


class TestGeneration:
    draft_id = ""

    def test_02_chat(self, client, user_a):
        resp = client.post(f"{PREFIX}/documents/chat", json={"prompt": "写需求"}, headers=user_a)
        assert resp.status_code == 200 and "reply" in resp.json()["data"]

    def test_03_generate(self, client, user_a):
        resp = client.post(f"{PREFIX}/documents/generate",
                           json={"doc_type": "需求", "title": "测试", "prompt": "生成"}, headers=user_a)
        assert resp.status_code == 200
        TestGeneration.draft_id = resp.json()["data"]["draft_id"]

    def test_04_quality_check(self, client, user_a):
        resp = client.post(f"{PREFIX}/documents/quality-check",
                           json={"content": "## 需求\n\n完整的文档内容。"}, headers=user_a)
        assert resp.status_code == 200 and resp.json()["data"]["score"] >= 80


class TestDrafts:
    created_id = ""

    def test_05_create(self, client, user_a):
        resp = client.post(f"{PREFIX}/documents/drafts",
                           json={"doc_type": "设计", "title": "草稿A", "content": "内容"}, headers=user_a)
        assert resp.status_code == 201
        TestDrafts.created_id = resp.json()["data"]["id"]

    def test_06_list(self, client, user_a):
        resp = client.get(f"{PREFIX}/documents/drafts", headers=user_a)
        assert resp.status_code == 200 and resp.json()["total"] >= 1

    def test_07_get_own(self, client, user_a):
        resp = client.get(f"{PREFIX}/documents/drafts/{TestDrafts.created_id}", headers=user_a)
        assert resp.status_code == 200 and resp.json()["data"]["title"] == "草稿A"

    def test_08_update_own(self, client, user_a):
        resp = client.put(f"{PREFIX}/documents/drafts/{TestDrafts.created_id}",
                          json={"title": "修改后"}, headers=user_a)
        assert resp.status_code == 200 and resp.json()["data"]["title"] == "修改后"

    def test_09_delete_own(self, client, user_a):
        r = client.post(f"{PREFIX}/documents/drafts", json={"doc_type": "接口", "title": "临时"}, headers=user_a)
        tmp_id = r.json()["data"]["id"]
        assert client.delete(f"{PREFIX}/documents/drafts/{tmp_id}", headers=user_a).status_code == 200


class TestOwnership:
    """user A's draft must not be accessible by user B."""

    def test_10_other_cannot_get(self, client, user_a, user_b):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "需求", "title": "A的"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.get(f"{PREFIX}/documents/drafts/{draft_id}", headers=user_b)
        assert resp.status_code == 403

    def test_11_other_cannot_update(self, client, user_a, user_b):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "需求", "title": "A的"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.put(f"{PREFIX}/documents/drafts/{draft_id}",
                          json={"title": "被篡改"}, headers=user_b)
        assert resp.status_code == 403

    def test_12_other_cannot_delete(self, client, user_a, user_b):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "需求", "title": "A的"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.delete(f"{PREFIX}/documents/drafts/{draft_id}", headers=user_b)
        assert resp.status_code == 403

    def test_13_other_cannot_export(self, client, user_a, user_b):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "需求", "title": "A的"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.get(f"{PREFIX}/documents/{draft_id}/export", headers=user_b)
        assert resp.status_code == 403

    def test_14_other_cannot_download(self, client, user_a, user_b):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "需求", "title": "A的"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.get(f"{PREFIX}/documents/{draft_id}/download", headers=user_b)
        assert resp.status_code == 403


class TestExportDownload:
    def test_15_export(self, client, user_a):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "手册", "title": "导出测试", "content": "导出内容"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.get(f"{PREFIX}/documents/{draft_id}/export?fmt=md", headers=user_a)
        assert resp.status_code == 200 and resp.json()["data"]["format"] == "md"

    def test_16_download(self, client, user_a):
        r = client.post(f"{PREFIX}/documents/drafts",
                        json={"doc_type": "接口", "title": "下载测试", "content": "下载内容"}, headers=user_a)
        draft_id = r.json()["data"]["id"]
        resp = client.get(f"{PREFIX}/documents/{draft_id}/download", headers=user_a)
        assert resp.status_code == 200 and resp.json()["data"]["filename"] == "下载测试.md"

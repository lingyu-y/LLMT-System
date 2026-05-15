"""第七部分 文档生成接口 — 11 端点统筹测试"""

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
def user_headers(db: Session):
    user = db.query(User).filter(User.username == "author").first()
    if user is None:
        user = User(username="author", password_hash=hash_password("pass1234"), status="active")
        db.add(user)
        db.commit()
        db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestDocumentModels:
    def test_01_list_models(self, client, user_headers):
        resp = client.get(f"{PREFIX}/documents/models", headers=user_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 3


class TestGeneration:
    def test_02_chat(self, client, user_headers):
        resp = client.post(
            f"{PREFIX}/documents/chat",
            json={"prompt": "写一份需求文档"},
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert "reply" in resp.json()["data"]

    def test_03_generate(self, client, user_headers):
        resp = client.post(
            f"{PREFIX}/documents/generate",
            json={"doc_type": "需求", "title": "测试文档", "prompt": "生成需求规格说明"},
            headers=user_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "draft_id" in data
        TestGeneration.draft_id = data["draft_id"]

    def test_04_quality_check(self, client, user_headers):
        resp = client.post(
            f"{PREFIX}/documents/quality-check",
            json={"content": "## 需求\n\n这是一份完整的需求规格说明文档，包含详细的功能描述。"},
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["score"] >= 80


class TestDrafts:
    created_id: str = ""

    def test_05_create_draft(self, client, user_headers):
        resp = client.post(
            f"{PREFIX}/documents/drafts",
            json={"doc_type": "设计", "title": "概要设计草稿", "content": "## 设计内容"},
            headers=user_headers,
        )
        assert resp.status_code == 201
        TestDrafts.created_id = resp.json()["data"]["id"]

    def test_06_list_drafts(self, client, user_headers):
        resp = client.get(f"{PREFIX}/documents/drafts", headers=user_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_07_get_draft(self, client, user_headers):
        resp = client.get(
            f"{PREFIX}/documents/drafts/{TestDrafts.created_id}",
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "概要设计草稿"

    def test_08_update_draft(self, client, user_headers):
        resp = client.put(
            f"{PREFIX}/documents/drafts/{TestDrafts.created_id}",
            json={"title": "修改后的草稿"},
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "修改后的草稿"

    def test_09_delete_draft(self, client, user_headers):
        # 创建临时草稿再删除
        resp = client.post(
            f"{PREFIX}/documents/drafts",
            json={"doc_type": "接口", "title": "临时"},
            headers=user_headers,
        )
        tmp_id = resp.json()["data"]["id"]
        resp = client.delete(
            f"{PREFIX}/documents/drafts/{tmp_id}",
            headers=user_headers,
        )
        assert resp.status_code == 200

    def test_10_draft_not_found(self, client, user_headers):
        resp = client.get(
            f"{PREFIX}/documents/drafts/nonexist",
            headers=user_headers,
        )
        assert resp.status_code == 404


class TestExportDownload:
    def test_11_export(self, client, user_headers):
        resp = client.post(
            f"{PREFIX}/documents/drafts",
            json={"doc_type": "用户手册", "title": "导出测试", "content": "导出内容"},
            headers=user_headers,
        )
        draft_id = resp.json()["data"]["id"]

        resp = client.get(
            f"{PREFIX}/documents/{draft_id}/export?fmt=md",
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["format"] == "md"

    def test_12_download(self, client, user_headers):
        resp = client.post(
            f"{PREFIX}/documents/drafts",
            json={"doc_type": "接口", "title": "下载测试", "content": "下载内容"},
            headers=user_headers,
        )
        draft_id = resp.json()["data"]["id"]

        resp = client.get(
            f"{PREFIX}/documents/{draft_id}/download",
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["filename"] == "下载测试.md"

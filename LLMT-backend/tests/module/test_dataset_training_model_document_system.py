"""Module tests for the main backend business modules."""

from io import BytesIO

import pytest
from fastapi import UploadFile

from app.models import ModelVersion, Role, User
from app.repositories import model_repository
from app.services import dataset_service


def _upload_file(name: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(data))


def test_dataset_upload_accepts_valid_text_file(monkeypatch, db_session, completed_dataset, fake_minio):
    monkeypatch.setattr(dataset_service, "get_minio_client", lambda: fake_minio)

    result = dataset_service.upload_file(
        db_session,
        completed_dataset,
        _upload_file("records.jsonl", b'{"text":"hello"}\n'),
        "alice",
    )

    assert result["success"] is True
    assert result["data_type"] == "text"
    assert completed_dataset.file_count == 2


def test_dataset_upload_rejects_illegal_extension(db_session, completed_dataset):
    result = dataset_service.upload_file(
        db_session,
        completed_dataset,
        _upload_file("payload.zip", b"PK\x03\x04"),
        "alice",
    )

    assert result["success"] is False
    assert "文件格式不支持" in result["error"]


def test_dataset_upload_rejects_storage_error(monkeypatch, db_session, completed_dataset):
    monkeypatch.setattr(dataset_service, "_check_storage_space", lambda *_: "存储空间不足")

    result = dataset_service.upload_file(
        db_session,
        completed_dataset,
        _upload_file("records.txt", b"hello"),
        "alice",
    )

    assert result["success"] is False
    assert result["error"] == "存储空间不足"


def test_training_task_create_accepts_valid_dataset(monkeypatch, app_client, completed_dataset, auth_headers):
    from app.services import training_service

    monkeypatch.setattr(training_service, "_run_task_in_background", lambda *_: None)

    response = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={
            "task_name": "module-train",
            "dataset_id": completed_dataset.id,
            "framework": "pytorch",
            "parallel_strategy": "ddp",
            "config": {"batch_size": 4, "learning_rate": 0.0001, "max_epochs": 2},
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["task_name"] == "module-train"


def test_training_task_create_rejects_invalid_parameters(app_client, completed_dataset, auth_headers):
    response = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={
            "task_name": "bad-train",
            "dataset_id": completed_dataset.id,
            "config": {"batch_size": 0},
        },
    )

    assert response.status_code == 422


def test_training_task_create_rejects_unprocessed_dataset(app_client, db_session, seeded_users, auth_headers):
    from app.models import Dataset

    dataset = Dataset(
        name="raw",
        data_type="text",
        version="v1.0.0",
        source="fixture",
        storage_path="datasets/raw",
        owner_id=seeded_users["user"].id,
        processing_status="pending",
        quality_status="unchecked",
    )
    db_session.add(dataset)
    db_session.commit()

    response = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={"task_name": "should-fail", "dataset_id": dataset.id},
    )

    assert response.status_code == 409
    assert "预处理" in response.json()["detail"]


def test_model_versions_can_be_listed(app_client, db_session, current_model):
    old = ModelVersion(
        model_name=current_model.model_name,
        model_code=current_model.model_code,
        version="v0.9.0",
        framework="pytorch",
        storage_path="models/llmt-gpt/v0.9.0",
        metrics_json={},
        hyperparams_json={},
        is_current=False,
    )
    db_session.add(old)
    db_session.commit()

    response = app_client.get(f"/api/v1/models/{current_model.model_code}/versions")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


def test_model_version_registration_requires_admin(app_client, current_model, auth_headers):
    response = app_client.post(
        f"/api/v1/models/{current_model.model_code}/versions",
        headers=auth_headers("alice"),
        json={"version": "v1.1.0", "model_name": "LLMT GPT"},
    )

    assert response.status_code == 403


def test_model_version_registration_creates_new_current_version(app_client, current_model, auth_headers):
    response = app_client.post(
        f"/api/v1/models/{current_model.model_code}/versions",
        headers=auth_headers("admin"),
        json={"version": "v1.1.0", "model_name": "LLMT GPT", "framework": "pytorch"},
    )

    assert response.status_code == 201
    assert response.json()["data"]["version"] == "v1.0.1"


def test_model_rollback_validates_version_and_returns_result(
    monkeypatch, app_client, db_session, current_model, fake_minio, auth_headers
):
    second = model_repository.create_model(
        db_session,
        model_name=current_model.model_name,
        model_code=current_model.model_code,
        framework="pytorch",
    )
    fake_minio.objects[("models", f"{current_model.storage_path}/weights.bin")] = b"weights"

    import app.api.v1.models as models_api

    monkeypatch.setattr(models_api, "get_minio_client", lambda: fake_minio)

    response = app_client.post(
        f"/api/v1/models/{current_model.model_code}/versions/{current_model.version}/rollback",
        headers=auth_headers("admin"),
        json={"reason": "module test"},
    )

    assert second.version == "v1.0.1"
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "v1.0.0"
    assert data["rollback"]["to_version"] == "v1.0.0"
    assert data["rollback"]["from_version"] == "v1.0.1"


def test_document_models_lists_current_models(app_client, current_model):
    response = app_client.get("/api/v1/documents/models")

    assert response.status_code == 200
    assert response.json()["data"][0]["value"] == current_model.model_code


def test_document_generate_calls_inference_logic(monkeypatch, app_client, current_model, auth_headers):
    import app.api.v1.documents as documents_api

    monkeypatch.setattr(documents_api, "_infer", lambda *_, **__: "生成的报告内容")

    response = app_client.post(
        "/api/v1/documents/generate",
        headers=auth_headers("alice"),
        json={"model_code": current_model.model_code, "doc_type": "report", "title": "训练报告"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["content"] == "生成的报告内容"


def test_document_generate_rejects_invalid_doc_type(app_client, current_model, auth_headers):
    response = app_client.post(
        "/api/v1/documents/generate",
        headers=auth_headers("alice"),
        json={"model_code": current_model.model_code, "doc_type": "slides", "title": "训练报告"},
    )

    assert response.status_code == 422


def test_system_users_query_allows_admin(app_client, seeded_users, auth_headers):
    response = app_client.get("/api/v1/system/users", headers=auth_headers("admin"))

    assert response.status_code == 200
    assert response.json()["total"] >= 2


def test_system_users_query_denies_normal_user(app_client, seeded_users, auth_headers):
    response = app_client.get("/api/v1/system/users", headers=auth_headers("alice"))

    assert response.status_code == 403


def test_system_role_update_changes_user_role(app_client, db_session, seeded_users, auth_headers):
    role = db_session.query(Role).filter(Role.name == "admin").first()
    user = db_session.query(User).filter(User.username == "alice").first()

    response = app_client.put(
        f"/api/v1/system/users/{user.id}/roles",
        headers=auth_headers("admin"),
        json={"role_ids": [role.id]},
    )

    assert response.status_code == 200
    db_session.refresh(user)
    assert [r.name for r in user.roles] == ["admin"]

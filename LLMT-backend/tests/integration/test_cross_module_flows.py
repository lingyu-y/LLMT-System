"""Integration tests for data passed across backend modules."""

from app.models import Dataset, TrainingTask
from app.repositories import model_repository, training_repository


def test_login_returns_role_scoped_menu_permissions(app_client, seeded_users):
    login = app_client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice123"})
    token = login.json()["token"]

    me = app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    admin_response = app_client.get("/api/v1/system/users", headers={"Authorization": f"Bearer {token}"})

    assert login.status_code == 200
    assert "system" not in me.json()["data"]["menuKeys"]
    assert admin_response.status_code == 403


def test_dataset_created_by_api_can_be_referenced_by_training_task(
    monkeypatch, app_client, db_session, auth_headers
):
    from app.services import training_service

    monkeypatch.setattr(training_service, "_run_task_in_background", lambda *_: None)

    created = app_client.post(
        "/api/v1/datasets",
        headers=auth_headers("alice"),
        json={
            "name": "integrated-dataset",
            "data_type": "text",
            "version": "v1.0.0",
            "storage_path": "datasets/integrated",
            "file_count": 1,
            "total_size": 20,
        },
    )
    dataset_id = created.json()["data"]["id"]
    dataset = db_session.query(Dataset).filter(Dataset.id == dataset_id).first()
    dataset.processing_status = "completed"
    dataset.quality_status = "passed"
    db_session.commit()

    task = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={
            "task_name": "integrated-train",
            "dataset_id": dataset_id,
            "framework": "pytorch",
            "parallel_strategy": "ddp",
        },
    )

    assert created.status_code == 201
    assert task.status_code == 200
    assert task.json()["data"]["dataset_id"] == dataset_id


def test_training_task_creation_fails_when_dataset_is_missing(app_client, auth_headers):
    response = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={"task_name": "missing-dataset", "dataset_id": 9999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "数据集不存在"


def test_completed_training_task_promotes_to_model_version(db_session, completed_dataset, seeded_users):
    task = training_repository.create_task(
        db_session,
        task_name="Promote Me",
        dataset_id=completed_dataset.id,
        creator_id=seeded_users["user"].id,
        framework="pytorch",
        parallel_strategy="ddp",
        config_json={"batch_size": 4, "learning_rate": 0.0001, "max_epochs": 1},
        max_epoch=1,
    )
    training_repository.update_status(db_session, task.id, status="completed")

    from app.services import training_service

    result = training_service.promote_to_model(db_session, task.id)
    versions = model_repository.get_versions(db_session, result["model_code"])

    assert result["version"] == "v1.0.0"
    assert versions[0].task_id == task.id


def test_model_rollback_checks_that_target_version_exists(db_session, current_model):
    missing = model_repository.get_model_by_code_and_version(db_session, current_model.model_code, "v9.9.9")

    assert missing is None


def test_document_generation_uses_current_model_metadata(monkeypatch, app_client, current_model, auth_headers):
    import app.api.v1.documents as documents_api

    captured = {}

    def fake_infer(model_code, prompt, max_tokens=256, db=None):
        captured["model_code"] = model_code
        captured["has_db"] = db is not None
        return "集成测试文档"

    monkeypatch.setattr(documents_api, "_infer", fake_infer)

    response = app_client.post(
        "/api/v1/documents/generate",
        headers=auth_headers("alice"),
        json={"model_code": current_model.model_code, "doc_type": "summary", "title": "训练摘要"},
    )

    assert response.status_code == 200
    assert captured == {"model_code": current_model.model_code, "has_db": True}
    assert response.json()["data"]["content"] == "集成测试文档"


def test_document_generation_reports_unavailable_model(db_session):
    import app.api.v1.documents as documents_api

    content = documents_api._infer("missing-model", "prompt", db=db_session)

    assert "未找到可用的文档生成模型" in content

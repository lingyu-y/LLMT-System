"""System-level API tests that exercise representative user flows."""

from app.models import Dataset


def test_main_business_flow_login_dataset_training_model_document(
    monkeypatch, app_client, db_session, completed_dataset, current_model
):
    import app.api.v1.documents as documents_api
    from app.services import training_service

    monkeypatch.setattr(training_service, "_run_task_in_background", lambda *_: None)
    monkeypatch.setattr(documents_api, "_infer", lambda *_, **__: "系统测试生成内容")

    login = app_client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice123"})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    datasets = app_client.get("/api/v1/datasets", headers=headers)
    task = app_client.post(
        "/api/v1/training/tasks",
        headers=headers,
        json={"task_name": "system-flow-train", "dataset_id": completed_dataset.id},
    )
    task_id = task.json()["data"]["id"]
    task_detail = app_client.get(f"/api/v1/training/tasks/{task_id}", headers=headers)
    models = app_client.get("/api/v1/models")
    document = app_client.post(
        "/api/v1/documents/generate",
        headers=headers,
        json={"model_code": current_model.model_code, "doc_type": "report", "title": "系统测试报告"},
    )
    me = app_client.get("/api/v1/auth/me", headers=headers)

    assert login.status_code == 200
    assert datasets.status_code == 200
    assert task.status_code == 200
    assert task_detail.json()["data"]["status"] in {"created", "queued"}
    assert models.json()["data"][0]["model_code"] == current_model.model_code
    assert document.json()["data"]["content"] == "系统测试生成内容"
    assert me.json()["data"]["username"] == "alice"


def test_protected_resource_rejects_unauthenticated_request(app_client):
    response = app_client.get("/api/v1/datasets")

    assert response.status_code == 401


def test_normal_user_is_denied_system_management(app_client, seeded_users):
    login = app_client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice123"})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    response = app_client.get("/api/v1/system/users", headers=headers)

    assert response.status_code == 403


def test_invalid_training_parameters_are_reported(app_client, completed_dataset, auth_headers):
    response = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={"task_name": "bad-system-task", "dataset_id": completed_dataset.id, "config": {"learning_rate": -1}},
    )

    assert response.status_code == 422


def test_missing_dataset_returns_business_error(app_client, auth_headers):
    response = app_client.post(
        "/api/v1/training/tasks",
        headers=auth_headers("alice"),
        json={"task_name": "missing-dataset", "dataset_id": 123456},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "数据集不存在"


def test_uploading_illegal_file_returns_error(monkeypatch, app_client, db_session, seeded_users, auth_headers, fake_minio):
    import app.services.dataset_service as dataset_service

    monkeypatch.setattr(dataset_service, "get_minio_client", lambda: fake_minio)
    dataset = Dataset(
        name="upload-target",
        data_type="text",
        version="v1.0.0",
        storage_path="datasets/upload-target",
        owner_id=seeded_users["user"].id,
    )
    db_session.add(dataset)
    db_session.commit()

    response = app_client.post(
        f"/api/v1/datasets/upload?dataset_id={dataset.id}",
        headers=auth_headers("alice"),
        files={"file": ("bad.exe", b"not allowed", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "文件格式不支持" in response.json()["detail"]

"""Unit tests for validation helpers and schema-level guards."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.schemas.dataset import DatasetCreate
from app.schemas.document import DocumentGenerateRequest, DraftSaveRequest
from app.schemas.model import ModelImport, VersionCreate
from app.schemas.training import TrainingConfigDict, TrainingTaskCreate
from app.services import dataset_service, training_service


def test_password_hash_and_verify_accepts_correct_password():
    hashed = hash_password("secret123")

    assert verify_password("secret123", hashed) is True


def test_password_verify_rejects_wrong_password():
    hashed = hash_password("secret123")

    assert verify_password("bad-secret", hashed) is False


def test_access_token_decodes_expected_subject():
    token = create_access_token({"sub": "42", "username": "alice"})

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["username"] == "alice"


def test_expired_access_token_returns_none():
    token = create_access_token({"sub": "42"}, expires_delta=timedelta(seconds=-1))

    assert decode_access_token(token) is None


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [("train.txt", "text"), ("samples.csv", "text"), ("doc.docx", "doc"), ("table.xlsx", "excel")],
)
def test_dataset_file_type_detection_accepts_supported_extensions(filename, expected_type):
    assert dataset_service._detect_data_type(filename) == expected_type


def test_dataset_file_type_detection_marks_unknown_extension():
    assert dataset_service._detect_data_type("archive.zip") == "other"


def test_dataset_filename_validation_rejects_illegal_characters():
    assert "非法字符" in dataset_service._validate_filename("bad/name.csv")


def test_dataset_schema_rejects_negative_file_size():
    with pytest.raises(ValidationError):
        DatasetCreate(name="demo", data_type="text", total_size=-1)


def test_training_config_accepts_reasonable_hyperparameters():
    config = TrainingConfigDict(batch_size=8, learning_rate=1e-4, max_epochs=3, num_gpus=2)

    assert config.batch_size == 8
    assert config.learning_rate == pytest.approx(1e-4)


@pytest.mark.parametrize(
    "payload",
    [
        {"batch_size": 0},
        {"learning_rate": 0},
        {"max_epochs": 0},
        {"train_split": 1.5},
    ],
)
def test_training_config_rejects_invalid_hyperparameters(payload):
    with pytest.raises(ValidationError):
        TrainingConfigDict(**payload)


def test_training_task_rejects_missing_dataset_id_range():
    with pytest.raises(ValidationError):
        TrainingTaskCreate(task_name="bad-task", dataset_id=0)


def test_training_validate_config_reports_incompatible_parallelism():
    config = TrainingConfigDict(num_gpus=1, tensor_model_parallel_size=2)

    result = training_service.validate_config(config, framework="deepspeed", strategy="zero2")

    assert result["valid"] is False
    assert result["errors"]


def test_model_version_schema_accepts_semver_style_version():
    body = VersionCreate(version="v1.2.3", model_name="demo")

    assert body.version == "v1.2.3"


def test_model_version_schema_rejects_non_semver_version():
    with pytest.raises(ValidationError):
        VersionCreate(version="latest")


def test_model_import_rejects_empty_source_path():
    with pytest.raises(ValidationError):
        ModelImport(source_path="", model_name="demo", model_code="demo", version="v1.0.0")


def test_document_generate_accepts_supported_type():
    body = DocumentGenerateRequest(model_code="llmt-gpt", doc_type="report", title="训练报告")

    assert body.doc_type == "report"


def test_document_generate_rejects_unsupported_type():
    with pytest.raises(ValidationError):
        DocumentGenerateRequest(model_code="llmt-gpt", doc_type="slides", title="演示")


def test_draft_save_rejects_empty_content():
    with pytest.raises(ValidationError):
        DraftSaveRequest(model_code="llmt-gpt", doc_type="summary", title="摘要", content="")

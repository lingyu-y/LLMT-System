"""Health check endpoints."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import (
    check_elasticsearch_connection,
    engine,
    get_influx_client,
    get_minio_client,
    settings,
)

router = APIRouter(prefix="/health", tags=["health"])


def _status_ok() -> dict[str, bool | None | str]:
    return {"status": True, "error": None}


def _status_error(exc: Exception) -> dict[str, bool | str]:
    return {"status": False, "error": str(exc)}


@router.get("")
def health_check():
    app_settings = get_settings()
    return {
        "status": "ok",
        "app": app_settings.APP_NAME,
        "env": app_settings.APP_ENV,
    }


@router.get("/databases")
def database_health_check():
    result: dict[str, dict[str, bool | None | str]] = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        result["postgresql"] = _status_ok()
    except Exception as exc:  # noqa: BLE001 - health check should report failures.
        result["postgresql"] = _status_error(exc)

    try:
        if get_influx_client().ping():
            result["influxdb"] = _status_ok()
        else:
            result["influxdb"] = {"status": False, "error": "InfluxDB ping returned false"}
    except Exception as exc:  # noqa: BLE001
        result["influxdb"] = _status_error(exc)

    try:
        client = get_minio_client()
        bucket = settings.MINIO_BUCKET_DATASETS
        client.bucket_exists(bucket)
        result["minio"] = _status_ok()
    except Exception as exc:  # noqa: BLE001
        result["minio"] = _status_error(exc)

    try:
        if check_elasticsearch_connection():
            result["elasticsearch"] = _status_ok()
        else:
            result["elasticsearch"] = {"status": False, "error": "Elasticsearch ping returned false"}
    except Exception as exc:  # noqa: BLE001
        result["elasticsearch"] = _status_error(exc)

    return result

"""Database and external storage clients."""

from collections.abc import Generator
from functools import lru_cache

from elasticsearch import Elasticsearch
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from minio import Minio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.base import Base

settings = get_settings()


def _create_engine():
    database_url = settings.postgres_database_url
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }

    if database_url.startswith("sqlite"):
        engine_kwargs = {"connect_args": {"check_same_thread": False}}

    return create_engine(database_url, **engine_kwargs)


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a SQLAlchemy session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@lru_cache
def get_influx_client() -> InfluxDBClient:
    """Return a reusable InfluxDB client."""

    return InfluxDBClient(
        url=settings.INFLUXDB_URL,
        token=settings.INFLUXDB_TOKEN,
        org=settings.INFLUXDB_ORG,
        timeout=settings.INFLUXDB_TIMEOUT_MS,
    )


def get_influx_write_api():
    """Return a synchronous write API for training metrics."""

    return get_influx_client().write_api(write_options=SYNCHRONOUS)


def get_influx_query_api():
    """Return a query API for training metrics."""

    return get_influx_client().query_api()


minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)


def get_minio_client() -> Minio:
    """Return the configured MinIO client."""

    return minio_client


def ensure_minio_buckets() -> list[str]:
    """Create configured buckets if they do not exist.

    This function is intentionally not called on import. It can be called from
    an application startup hook or a local setup script.
    """

    client = get_minio_client()
    ensured: list[str] = []
    for bucket in settings.minio_buckets:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        ensured.append(bucket)
    return ensured


def _create_elasticsearch_client() -> Elasticsearch:
    username = settings.ELASTICSEARCH_USERNAME
    password = settings.ELASTICSEARCH_PASSWORD

    if username and password:
        return Elasticsearch(settings.ELASTICSEARCH_URL, basic_auth=(username, password))
    return Elasticsearch(settings.ELASTICSEARCH_URL)


es_client = _create_elasticsearch_client()


def get_elasticsearch_client() -> Elasticsearch:
    """Return the configured Elasticsearch client."""

    return es_client


def check_elasticsearch_connection() -> bool:
    """Return whether Elasticsearch is reachable."""

    return bool(get_elasticsearch_client().ping())

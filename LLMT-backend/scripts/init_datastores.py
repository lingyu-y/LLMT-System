"""Initialize all backend datastores for local development.

This script is intentionally idempotent. It can be run multiple times to:
1. apply PostgreSQL schema migrations via Alembic
2. ensure the InfluxDB bucket exists
3. ensure MinIO buckets exist
4. ensure the Elasticsearch log index exists
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.core.database import (  # noqa: E402
    ensure_minio_buckets,
    get_elasticsearch_client,
    get_influx_client,
)

settings = get_settings()


def run_postgres_migrations() -> None:
    """Apply all Alembic migrations to PostgreSQL."""

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


def ensure_influxdb_bucket() -> str:
    """Create the configured InfluxDB bucket when missing."""

    client = get_influx_client()
    bucket_api = client.buckets_api()
    bucket = bucket_api.find_bucket_by_name(settings.INFLUXDB_BUCKET)
    if bucket is not None:
        return settings.INFLUXDB_BUCKET

    org_api = client.organizations_api()
    org = org_api.find_organization(org=settings.INFLUXDB_ORG)
    if org is None:
        raise RuntimeError(
            f"InfluxDB organization '{settings.INFLUXDB_ORG}' was not found."
        )

    bucket_api.create_bucket(
        bucket_name=settings.INFLUXDB_BUCKET,
        org_id=org.id,
        description="Training metrics bucket for LLMT backend.",
    )
    return settings.INFLUXDB_BUCKET


def ensure_elasticsearch_index() -> str:
    """Create the configured Elasticsearch log index when missing."""

    client = get_elasticsearch_client()
    index_name = settings.ELASTICSEARCH_INDEX_LOGS
    index_settings = {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }
    try:
        policy_name = f"{index_name}-{settings.ELASTICSEARCH_LOG_RETENTION_DAYS}d-retention"
        client.ilm.put_lifecycle(
            name=policy_name,
            policy={
                "phases": {
                    "delete": {
                        "min_age": f"{settings.ELASTICSEARCH_LOG_RETENTION_DAYS}d",
                        "actions": {"delete": {}},
                    }
                }
            },
        )
        index_settings["index"]["lifecycle.name"] = policy_name
    except Exception:
        pass
    mappings = {
        "properties": {
            "id": {"type": "long"},
            "timestamp": {"type": "date"},
            "created_at": {"type": "date"},
            "level": {"type": "keyword"},
            "category": {"type": "keyword"},
            "module": {"type": "keyword"},
            "message": {"type": "text"},
            "detail": {"type": "text"},
            "action": {"type": "keyword"},
            "resource": {"type": "keyword"},
            "resource_id": {"type": "long"},
            "user_id": {"type": "integer"},
            "username": {"type": "keyword"},
            "ip_address": {"type": "keyword"},
            "task_id": {"type": "long"},
            "task_code": {"type": "keyword"},
            "step": {"type": "long"},
            "trace_id": {"type": "keyword"},
        }
    }

    if client.indices.exists(index=index_name):
        client.indices.put_mapping(index=index_name, properties=mappings["properties"])
        if "lifecycle.name" in index_settings["index"]:
            client.indices.put_settings(
                index=index_name,
                settings={"index": {"lifecycle.name": index_settings["index"]["lifecycle.name"]}},
            )
        return index_name

    client.indices.create(
        index=index_name,
        settings=index_settings,
        mappings=mappings,
    )
    return index_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize PostgreSQL, InfluxDB, MinIO, and Elasticsearch.",
    )
    parser.add_argument(
        "--skip-postgres",
        action="store_true",
        help="Skip Alembic migrations for PostgreSQL.",
    )
    parser.add_argument(
        "--skip-influxdb",
        action="store_true",
        help="Skip InfluxDB bucket initialization.",
    )
    parser.add_argument(
        "--skip-minio",
        action="store_true",
        help="Skip MinIO bucket initialization.",
    )
    parser.add_argument(
        "--skip-elasticsearch",
        action="store_true",
        help="Skip Elasticsearch index initialization.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    steps: list[tuple[str, str]] = []

    try:
        if not args.skip_postgres:
            run_postgres_migrations()
            steps.append(("postgresql", "migrations applied"))

        if not args.skip_influxdb:
            bucket_name = ensure_influxdb_bucket()
            steps.append(("influxdb", f"bucket ready: {bucket_name}"))

        if not args.skip_minio:
            buckets = ensure_minio_buckets()
            steps.append(("minio", f"buckets ready: {', '.join(buckets)}"))

        if not args.skip_elasticsearch:
            index_name = ensure_elasticsearch_index()
            steps.append(("elasticsearch", f"index ready: {index_name}"))
    except Exception as exc:  # noqa: BLE001 - command line init should print reason.
        print(f"[init] failed: {exc}")
        return 1

    for name, message in steps:
        print(f"[init] {name}: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

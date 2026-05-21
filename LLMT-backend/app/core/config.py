"""Application configuration."""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Unified settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "LLMT-backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "离线大数据训练与应用系统"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api"
    SECRET_KEY: str = "change-this-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "llmt_system"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DATABASE_URL: str | None = Field(default=None)

    INFLUXDB_URL: str = "http://localhost:8086"
    INFLUXDB_TOKEN: str = "change-this-influxdb-token"
    INFLUXDB_ORG: str = "llmt"
    INFLUXDB_BUCKET: str = "training_metrics"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_DATASETS: str = "datasets"
    MINIO_BUCKET_MODELS: str = "models"
    MINIO_BUCKET_CHECKPOINTS: str = "checkpoints"
    MINIO_SECURE: bool = False

    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_USERNAME: str | None = None
    ELASTICSEARCH_PASSWORD: str | None = None
    ELASTICSEARCH_INDEX_LOGS: str = "system-logs"

    # Redis / Celery
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB_BROKER: int = 0
    REDIS_DB_BACKEND: int = 1

    # Training framework
    LLMT_TRAINING_MODULE_PATH: str = "llmt_training"
    LLMT_TRAINING_SCRIPTS_DIR: str | None = None  # absolute path to LLMT-training/examples/
    TRAINING_DEFAULT_TIMEOUT_HOURS: int = 168  # 7 days

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        """Accept common deployment words in addition to true/false."""

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value

    @property
    def redis_url_broker(self) -> str:
        """Return Redis URL for Celery broker."""
        password = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_BROKER}"

    @property
    def redis_url_backend(self) -> str:
        """Return Redis URL for Celery result backend."""
        password = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_BACKEND}"

    @property
    def postgres_database_url(self) -> str:
        """Return explicit PostgreSQL URL or build one from connection fields."""

        if self.POSTGRES_DATABASE_URL:
            return self.POSTGRES_DATABASE_URL

        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def minio_buckets(self) -> list[str]:
        return [
            self.MINIO_BUCKET_DATASETS,
            self.MINIO_BUCKET_MODELS,
            self.MINIO_BUCKET_CHECKPOINTS,
        ]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()

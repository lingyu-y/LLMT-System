"""Celery application initialization."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "llmt-training",
    broker=settings.redis_url_broker,
    backend=settings.redis_url_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.TRAINING_DEFAULT_TIMEOUT_HOURS * 3600,
)

celery_app.autodiscover_tasks(["app.tasks"])

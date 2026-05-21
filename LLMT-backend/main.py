"""Application entrypoint — kept at project root to avoid app/app namespace collision."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

application = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

application.include_router(api_router, prefix=settings.API_PREFIX)


@application.on_event("startup")
def bootstrap_development_data() -> None:
    from app.services.bootstrap_service import ensure_bootstrap_data
    ensure_bootstrap_data()


# Register Celery tasks (import to register with the broker)
try:
    from app.core.celery_app import celery_app  # noqa: F401
    import app.tasks.training_tasks  # noqa: F401
except Exception:
    pass  # Celery/Redis not available in dev mode

app = application

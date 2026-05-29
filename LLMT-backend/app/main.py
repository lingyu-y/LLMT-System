"""Application entrypoint."""

from importlib import import_module

from fastapi import FastAPI, Request

from app.api.router import api_router
from app.core.config import get_settings
from app.services.bootstrap_service import ensure_bootstrap_data

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.middleware("http")
async def index_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        try:
            from app.services import log_service
            log_service.index_log(
                level="ERROR",
                module="app.exception",
                message=str(exc),
                category="exception",
                action="unhandled_exception",
                resource=request.url.path,
                ip_address=request.client.host if request.client else "",
                extra={"method": request.method},
            )
        except Exception:
            pass
        raise


@app.on_event("startup")
def bootstrap_development_data() -> None:
    ensure_bootstrap_data()


# Register Celery tasks (import to register with the broker)
try:
    from app.core.celery_app import celery_app  # noqa: F401
    import_module("app.tasks.training_tasks")
except Exception:
    pass  # Celery/Redis not available in dev mode

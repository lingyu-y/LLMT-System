"""API router definitions."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.datasets import router as datasets_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.inference import router as inference_router
from app.api.v1.models import router as models_router
from app.api.v1.system import router as system_router
from app.api.v1.training import router as training_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(datasets_router)
api_router.include_router(inference_router)
api_router.include_router(documents_router)
api_router.include_router(models_router)
api_router.include_router(system_router)
api_router.include_router(training_router)

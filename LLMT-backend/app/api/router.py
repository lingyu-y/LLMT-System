"""API router definitions."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.models import router as models_router
from app.api.v1.resources import router as resources_router
from app.api.v1.system import router as system_router
from app.api.v1.training import router as training_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(models_router)
api_router.include_router(resources_router)
api_router.include_router(system_router)
api_router.include_router(training_router)

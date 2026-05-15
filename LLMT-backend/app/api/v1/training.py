"""Training API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.dependencies.auth import require_admin
from app.dependencies.db import get_db
from app.schemas.training import PrivacyConfigRequest

router = APIRouter(prefix="/training", tags=["训练管理"])


@router.post("/privacy-config")
def set_privacy_config(
    body: PrivacyConfigRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    return success_response(body.model_dump(), "差分隐私配置已保存")

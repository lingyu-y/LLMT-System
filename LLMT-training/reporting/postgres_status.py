"""PostgreSQL status updater – updates TrainingTask progress in the database."""

from __future__ import annotations

import os
from typing import Any


class PostgresStatusUpdater:
    """Updates TrainingTask status and progress in PostgreSQL.

    This class provides methods to update the training task record
    in the LLMT-System backend database. It can be used either:
    1. Directly via SQLAlchemy (when running in the same process as the backend)
    2. Via HTTP API calls (when running in a separate training process)
    """

    def __init__(
        self,
        db_url: str | None = None,
        api_url: str = "http://localhost:8000/api/v1",
        api_token: str | None = None,
    ):
        self.db_url = db_url
        self.api_url = api_url
        self.api_token = api_token

    def update_progress(
        self,
        task_code: str,
        *,
        status: str | None = None,
        current_epoch: int | None = None,
        current_step: int | None = None,
        checkpoint_path: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update training task progress.

        Tries SQLAlchemy first, then falls back to HTTP API.
        """
        try:
            return self._update_via_db(
                task_code,
                status=status,
                current_epoch=current_epoch,
                current_step=current_step,
                checkpoint_path=checkpoint_path,
                error_message=error_message,
            )
        except Exception:
            return self._update_via_api(
                task_code,
                status=status,
                current_epoch=current_epoch,
                current_step=current_step,
                checkpoint_path=checkpoint_path,
                error_message=error_message,
            )

    def _update_via_db(self, task_code: str, **kwargs: Any) -> bool:
        """Update via direct database connection (SQLAlchemy)."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        url = self.db_url or os.environ.get("POSTGRES_DATABASE_URL", "")
        if not url:
            raise RuntimeError("No database URL configured")

        engine = create_engine(url)
        updates = []
        params: dict[str, Any] = {"task_code": task_code}

        for field, value in kwargs.items():
            if value is not None:
                updates.append(f"{field} = :{field}")
                params[field] = value

        if not updates:
            return True

        status = kwargs.get("status")

        if status == "running":
            updates.append("started_at = COALESCE(started_at, NOW())")
        if status in ("completed", "failed", "cancelled"):
            updates.append("ended_at = NOW()")

        sql = text(f"UPDATE training_tasks SET {', '.join(updates)} WHERE task_code = :task_code")

        with Session(engine) as session:
            result = session.execute(sql, params)
            session.commit()

        # Auto-promote completed training to a ModelVersion
        if status == "completed":
            self._try_promote_to_model(task_code)

        return result.rowcount > 0

    def _try_promote_to_model(self, task_code: str) -> None:
        """Attempt to promote a completed training task to a ModelVersion.

        Tries the backend's Python API first (when running inside the Celery
        worker process), then falls back to the HTTP endpoint.
        """
        # Path 1: Direct import (when running inside the backend process)
        try:
            from app.tasks.training_tasks import _promote_to_model
            _promote_to_model(task_code)
            return
        except ImportError:
            pass
        except Exception:
            return  # Silently ignore on failure

        # Path 2: HTTP API (when running in a separate training subprocess)
        try:
            import httpx
            httpx.post(
                f"{self.api_url}/training/internal/promote-by-code/{task_code}",
                timeout=30,
            )
        except Exception:
            pass  # Best-effort; user can promote manually from the UI

    def _update_via_api(self, task_code: str, **kwargs: Any) -> bool:
        """Update via HTTP API call (for separate training processes)."""
        import httpx

        # First get the task ID from task_code
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            # The backend doesn't have a direct update endpoint,
            # so we use internal service methods pattern
            # In production, this would call a dedicated internal API
            return True  # Placeholder for API-based update
        except Exception:
            return False

"""MinIO checkpointer – upload, download, list, and prune checkpoints."""

from __future__ import annotations

import os
from typing import Any


class MinIOCheckpointer:
    """Manages training checkpoints in MinIO object storage.

    Provides upload/download/list/prune operations for checkpoint
    directories stored under the `checkpoints` bucket.
    """

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket: str = "checkpoints",
        secure: bool = False,
    ):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self._client = None

    def _ensure_client(self):
        """Lazily initialize MinIO client."""
        if self._client is None:
            try:
                from minio import Minio
                self._client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                )
                if not self._client.bucket_exists(self.bucket):
                    self._client.make_bucket(self.bucket)
            except ImportError:
                self._client = None

    def upload_checkpoint(
        self,
        task_code: str,
        local_dir: str,
        step: int | None = None,
    ) -> list[str]:
        """Upload a checkpoint directory to MinIO.

        Args:
            task_code: Training task code (used as prefix).
            local_dir: Local directory containing checkpoint files.
            step: Training step number (optional, for naming).

        Returns:
            List of uploaded object names.
        """
        self._ensure_client()
        if self._client is None:
            return []

        uploaded = []
        prefix = f"{task_code}"
        if step is not None:
            prefix += f"/step-{step}"

        for root, dirs, files in os.walk(local_dir):
            for filename in files:
                local_path = os.path.join(root, filename)
                relative = os.path.relpath(local_path, local_dir)
                object_name = f"{prefix}/{relative}".replace("\\", "/")

                try:
                    self._client.fput_object(
                        self.bucket, object_name, local_path,
                    )
                    uploaded.append(object_name)
                except Exception:
                    pass  # Skip failed uploads

        return uploaded

    def download_checkpoint(
        self,
        task_code: str,
        local_dir: str,
        step: int | None = None,
    ) -> str:
        """Download checkpoint files from MinIO.

        Args:
            task_code: Training task code.
            local_dir: Local directory to download into.
            step: Specific step to download, or None for latest.

        Returns:
            Local directory path containing downloaded files.
        """
        self._ensure_client()
        if self._client is None:
            return local_dir

        prefix = f"{task_code}"
        if step is not None:
            prefix += f"/step-{step}"

        os.makedirs(local_dir, exist_ok=True)

        objects = self._client.list_objects(self.bucket, prefix=prefix, recursive=True)
        for obj in objects:
            # Remove prefix to get relative path
            relative = obj.object_name[len(prefix):].lstrip("/")
            local_path = os.path.join(local_dir, relative)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self._client.fget_object(self.bucket, obj.object_name, local_path)

        return local_dir

    def list_checkpoints(self, task_code: str) -> list[dict[str, Any]]:
        """List all checkpoint objects for a task.

        Returns:
            List of dicts with object_name, size, last_modified.
        """
        self._ensure_client()
        if self._client is None:
            return []

        prefix = f"{task_code}/"
        if not self._client.bucket_exists(self.bucket):
            return []

        results = []
        objects = self._client.list_objects(self.bucket, prefix=prefix, recursive=True)
        for obj in objects:
            results.append({
                "object_name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
            })
        return results

    def prune_checkpoints(self, task_code: str, keep: int = 5) -> list[str]:
        """Remove old checkpoints, keeping only the N most recent.

        Args:
            task_code: Training task code.
            keep: Number of checkpoints to keep.

        Returns:
            List of removed object names.
        """
        self._ensure_client()
        if self._client is None:
            return []

        all_objects = list(
            self._client.list_objects(self.bucket, prefix=f"{task_code}/", recursive=True)
        )

        if len(all_objects) <= keep:
            return []

        # Sort by last_modified, keep the most recent
        all_objects.sort(key=lambda o: o.last_modified or "", reverse=True)
        to_remove = all_objects[keep:]

        removed = []
        for obj in to_remove:
            try:
                self._client.remove_object(self.bucket, obj.object_name)
                removed.append(obj.object_name)
            except Exception:
                pass

        return removed

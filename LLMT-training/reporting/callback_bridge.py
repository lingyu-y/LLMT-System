"""Reporting callback bridge – adapts TrainingCallback to InfluxDB + PostgreSQL + MinIO."""

from __future__ import annotations

from typing import Any

from llmt_training.core.callbacks import TrainingCallback
from llmt_training.core.state import TrainingState
from llmt_training.reporting.influxdb_writer import InfluxDBMetricsWriter
from llmt_training.reporting.postgres_status import PostgresStatusUpdater
from llmt_training.reporting.minio_checkpointer import MinIOCheckpointer
import os


class ReportingCallbackBridge(TrainingCallback):
    """Unified callback that reports to InfluxDB, PostgreSQL, and MinIO.

    This is the primary integration point between the training framework
    and the LLMT-System backend services.
    """

    def __init__(
        self,
        task_code: str,
        influxdb_writer: InfluxDBMetricsWriter | None = None,
        postgres_updater: PostgresStatusUpdater | None = None,
        minio_checkpointer: MinIOCheckpointer | None = None,
        report_interval_steps: int = 10,
        report_gpu_metrics: bool = True,
    ):
        self.task_code = task_code
        self.influxdb_writer = influxdb_writer
        self.postgres_updater = postgres_updater
        self.minio_checkpointer = minio_checkpointer
        self.report_interval_steps = report_interval_steps
        self.report_gpu_metrics = report_gpu_metrics
        self._step_count = 0

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ReportingCallbackBridge":
        """Create a ReportingCallbackBridge from a training config dict."""
        reporting = config.get("reporting", {})
        task_code = config.get("task_code", "")

        influxdb_writer = InfluxDBMetricsWriter(
            url=reporting.get("influxdb_url", "http://localhost:8086"),
            token=reporting.get("influxdb_token", ""),
            org=reporting.get("influxdb_org", "llmt"),
            bucket=reporting.get("influxdb_bucket", "training_metrics"),
        )

        # Prefer an explicit DB URL passed in the backend-generated config;
        # fall back to the POSTGRES_DATABASE_URL environment variable.
        postgres_db_url = reporting.get("postgres_db_url") or os.environ.get("POSTGRES_DATABASE_URL")
        postgres_updater = PostgresStatusUpdater(db_url=postgres_db_url)

        minio_checkpointer = MinIOCheckpointer()

        return cls(
            task_code=task_code,
            influxdb_writer=influxdb_writer,
            postgres_updater=postgres_updater,
            minio_checkpointer=minio_checkpointer,
            report_interval_steps=reporting.get("report_interval_steps", 10),
            report_gpu_metrics=reporting.get("report_gpu_metrics", True),
        )

    def on_train_begin(self, state: TrainingState, **kwargs: Any) -> None:
        """Mark task as running in PostgreSQL."""
        if self.postgres_updater:
            self.postgres_updater.update_progress(
                self.task_code, status="running",
                current_epoch=0, current_step=0,
            )

    def on_train_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Flush metrics and mark task as completed/failed."""
        if self.influxdb_writer:
            self.influxdb_writer.flush()
            self.influxdb_writer.close()

        if self.postgres_updater:
            self.postgres_updater.update_progress(
                self.task_code,
                status=state.status,
                current_epoch=state.epoch,
                current_step=state.global_step,
                error_message=state.error_message,
            )

    def on_step_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Report step metrics at configured intervals."""
        self._step_count += 1

        interval = max(1, self.report_interval_steps)
        if self._step_count != 1 and self._step_count % interval != 0:
            return

        if self.influxdb_writer:
            self.influxdb_writer.write_step_metrics(state)

            if self.report_gpu_metrics:
                self._collect_gpu_metrics(state)
                self.influxdb_writer.write_gpu_metrics(state)

        if self.postgres_updater:
            self.postgres_updater.update_progress(
                self.task_code,
                current_epoch=state.epoch,
                current_step=state.global_step,
            )

    def on_checkpoint(self, state: TrainingState, **kwargs: Any) -> None:
        """Upload checkpoint to MinIO."""
        checkpoint_path = kwargs.get("checkpoint_path", "")
        if self.minio_checkpointer and checkpoint_path:
            self.minio_checkpointer.upload_checkpoint(
                task_code=self.task_code,
                local_dir=checkpoint_path,
                step=state.global_step,
            )

    def on_error(self, state: TrainingState, **kwargs: Any) -> None:
        """Flush metrics and update status on error."""
        if self.influxdb_writer:
            self.influxdb_writer.flush()

        if self.postgres_updater:
            self.postgres_updater.update_progress(
                self.task_code,
                status="failed",
                current_epoch=state.epoch,
                current_step=state.global_step,
                error_message=state.error_message,
            )

    @staticmethod
    def _collect_gpu_metrics(state: TrainingState) -> None:
        """Collect GPU utilization metrics using torch.cuda."""
        try:
            import torch
            if torch.cuda.is_available():
                device = torch.cuda.current_device()
                state.gpu_memory_used_mb = torch.cuda.memory_allocated(device) / 1024 / 1024
                state.gpu_memory_total_mb = torch.cuda.get_device_properties(device).total_mem / 1024 / 1024
        except Exception:
            pass

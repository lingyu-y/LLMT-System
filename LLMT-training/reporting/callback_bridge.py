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
        upload_to_minio: bool = True,
        max_checkpoints: int = 2,
    ):
        self.task_code = task_code
        self.influxdb_writer = influxdb_writer
        self.postgres_updater = postgres_updater
        self.minio_checkpointer = minio_checkpointer
        self.report_interval_steps = report_interval_steps
        self.report_gpu_metrics = report_gpu_metrics
        self.upload_to_minio = upload_to_minio
        self.max_checkpoints = max(1, max_checkpoints)
        self._step_count = 0
        self._last_report_step = 0
        self._last_report_elapsed = 0.0

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ReportingCallbackBridge":
        """Create a ReportingCallbackBridge from a training config dict."""
        reporting = config.get("reporting", {})
        checkpoint = config.get("checkpoint", {})
        task_code = config.get("task_code", "")

        influxdb_writer = InfluxDBMetricsWriter(
            url=reporting.get("influxdb_url", "http://localhost:8086"),
            token=reporting.get("influxdb_token", ""),
            org=reporting.get("influxdb_org", "llmt"),
            bucket=reporting.get("influxdb_bucket", "training_metrics"),
            timeout_ms=reporting.get("influxdb_timeout_ms", 3000),
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
            upload_to_minio=checkpoint.get("upload_to_minio", True),
            max_checkpoints=checkpoint.get("max_checkpoints", 2),
        )

    def on_train_begin(self, state: TrainingState, **kwargs: Any) -> None:
        """Mark task as running in PostgreSQL."""
        if self.postgres_updater:
            is_resume = state.global_step > 0 or state.epoch > 0
            self.postgres_updater.update_progress(
                self.task_code, status="running",
                current_epoch=state.epoch,
                current_step=state.global_step,
            )
            if is_resume:
                self.postgres_updater.append_log(
                    self.task_code, "INFO",
                    f"训练已恢复 — 从 Epoch {state.epoch + 1}, Step {state.global_step} 继续",
                    step=state.global_step,
                )
            else:
                total_steps = state.max_steps or self._read_total_steps_from_db()
                self.postgres_updater.append_log(
                    self.task_code, "INFO",
                    f"训练开始 — 总 epoch: {state.max_epochs}, 总 step: {total_steps or '不限'}",
                )

    def on_epoch_begin(self, state: TrainingState, **kwargs: Any) -> None:
        if self.postgres_updater:
            self.postgres_updater.append_log(
                self.task_code, "INFO",
                f"Epoch {state.epoch + 1} 开始",
                step=state.global_step,
            )

    def on_epoch_end(self, state: TrainingState, **kwargs: Any) -> None:
        if self.postgres_updater:
            self.postgres_updater.append_log(
                self.task_code, "INFO",
                f"Epoch {state.epoch + 1} 完成 — loss: {state.loss:.4f}",
                step=state.global_step,
            )

    def on_train_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Flush metrics and mark task as completed/failed."""
        if self.influxdb_writer:
            self.influxdb_writer.write_step_metrics(state)
            if self.report_gpu_metrics:
                self._collect_gpu_metrics(state)
                self.influxdb_writer.write_gpu_metrics(state)
            if state.global_step > self._last_report_step:
                step_delta = state.global_step - self._last_report_step
                elapsed_delta = max(0.0, state.elapsed_seconds - self._last_report_elapsed)
                if elapsed_delta > 0:
                    self.influxdb_writer.write_communication_metrics(
                        self.task_code,
                        {"latency_ms": elapsed_delta / step_delta * 1000},
                    )
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
            if state.status == "paused":
                self.postgres_updater.append_log(
                    self.task_code, "WARN",
                    f"训练已暂停 — 在 Epoch {state.epoch + 1}, Step {state.global_step} 处暂停",
                    step=state.global_step,
                )
            elif state.status == "cancelled":
                self.postgres_updater.append_log(
                    self.task_code, "WARN",
                    f"训练已取消 — 在 Epoch {state.epoch + 1}, Step {state.global_step} 处取消",
                    step=state.global_step,
                )
            else:
                level = "ERROR" if state.status == "failed" else "INFO"
                self.postgres_updater.append_log(
                    self.task_code, level,
                    f"训练{'失败' if state.status == 'failed' else '完成'} — "
                    f"epoch: {state.epoch + 1}, step: {state.global_step}, "
                    f"final_loss: {state.loss:.4f}"
                    + (f", error: {state.error_message}" if state.error_message else ""),
                    step=state.global_step,
                )

    def on_step_end(self, state: TrainingState, **kwargs: Any) -> None:
        """Report step metrics at configured intervals."""
        if "loss" in kwargs:
            state.loss = float(kwargs["loss"])
        if "lr" in kwargs:
            state.learning_rate = float(kwargs["lr"])
        if "grad_norm" in kwargs:
            state.grad_norm = float(kwargs["grad_norm"])
        if "throughput" in kwargs:
            state.throughput = float(kwargs["throughput"])
        if "accuracy" in kwargs:
            state.custom_metrics["accuracy"] = float(kwargs["accuracy"])

        self._step_count += 1

        interval = max(1, self.report_interval_steps)
        if self._step_count != 1 and self._step_count % interval != 0:
            return

        if self.influxdb_writer:
            self.influxdb_writer.write_step_metrics(state)

            if self.report_gpu_metrics:
                self._collect_gpu_metrics(state)
                self.influxdb_writer.write_gpu_metrics(state)

            step_delta = max(1, state.global_step - self._last_report_step)
            elapsed_delta = max(0.0, state.elapsed_seconds - self._last_report_elapsed)
            if elapsed_delta > 0:
                self.influxdb_writer.write_communication_metrics(
                    self.task_code,
                    {"latency_ms": elapsed_delta / step_delta * 1000},
                )
            self._last_report_step = state.global_step
            self._last_report_elapsed = state.elapsed_seconds

        if self.postgres_updater:
            self.postgres_updater.update_progress(
                self.task_code,
                current_epoch=state.epoch,
                current_step=state.global_step,
            )
            self.postgres_updater.append_log(
                self.task_code, "INFO",
                f"Epoch {state.epoch + 1} — Step {state.global_step} — "
                f"loss: {state.loss:.4f} — lr: {state.learning_rate:.2e}",
                step=state.global_step,
            )

    def on_checkpoint(self, state: TrainingState, **kwargs: Any) -> None:
        """Upload checkpoint to MinIO."""
        checkpoint_path = kwargs.get("checkpoint_path", "")
        if self.minio_checkpointer and checkpoint_path and self.upload_to_minio:
            self.minio_checkpointer.upload_checkpoint(
                task_code=self.task_code,
                local_dir=checkpoint_path,
                step=state.global_step,
            )
            self.minio_checkpointer.prune_checkpoints(
                task_code=self.task_code,
                keep=self.max_checkpoints,
            )
        if self.postgres_updater:
            self.postgres_updater.append_log(
                self.task_code, "INFO",
                f"Checkpoint 已保存 — Step {state.global_step}",
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
            self.postgres_updater.append_log(
                self.task_code, "ERROR",
                f"训练出错 — Step {state.global_step}: {state.error_message}",
                step=state.global_step,
            )

    def _read_total_steps_from_db(self) -> int | None:
        """Read _total_steps from the task's config_json stored at training start."""
        import json as _json
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import Session
            url = self.postgres_updater.db_url if self.postgres_updater else None
            if not url:
                return None
            engine = create_engine(url)
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT config_json FROM training_tasks WHERE task_code = :tc"),
                    {"tc": self.task_code},
                ).fetchone()
                if row is None:
                    return None
                raw = row[0]
                cfg = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
                return cfg.get("_total_steps")
        except Exception:
            return None

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

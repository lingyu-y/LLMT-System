"""InfluxDB metrics writer – batch writes training metrics to InfluxDB."""

from __future__ import annotations

import time
from typing import Any

from llmt_training.core.state import TrainingState


class InfluxDBMetricsWriter:
    """Writes training metrics to InfluxDB in batches.

    Measurements:
      - training_step: loss, lr, grad_norm, throughput
      - gpu_metrics: memory_used_mb, memory_total_mb, utilization_pct
      - communication_metrics: all_reduce_latency_ms, all_gather_latency_ms
    """

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "llmt",
        bucket: str = "training_metrics",
        batch_size: int = 50,
        flush_interval: float = 5.0,
    ):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self._client = None
        self._write_api = None
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = time.time()

    def _ensure_client(self):
        """Lazily initialize InfluxDB client."""
        if self._client is None:
            try:
                from influxdb_client import InfluxDBClient
                from influxdb_client.client.write_api import SYNCHRONOUS

                self._client = InfluxDBClient(
                    url=self.url, token=self.token, org=self.org,
                )
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            except ImportError:
                self._write_api = None

    def write_step_metrics(self, state: TrainingState, **kwargs: Any) -> None:
        """Queue a training step metric point."""
        point = {
            "measurement": "training_step",
            "tags": {"task_code": state.task_code},
            "fields": {
                "loss": float(state.loss),
                "learning_rate": float(state.learning_rate),
                "grad_norm": float(state.grad_norm),
                "throughput": float(state.throughput),
                "epoch": state.epoch,
                "step": state.global_step,
                "elapsed_seconds": state.elapsed_seconds,
            },
        }
        self._buffer.append(point)
        self._maybe_flush()

    def write_gpu_metrics(self, state: TrainingState, **kwargs: Any) -> None:
        """Queue a GPU metric point."""
        point = {
            "measurement": "gpu_metrics",
            "tags": {"task_code": state.task_code},
            "fields": {
                "memory_used_mb": float(state.gpu_memory_used_mb),
                "memory_total_mb": float(state.gpu_memory_total_mb),
                "utilization_pct": float(state.gpu_utilization_pct),
                "epoch": state.epoch,
                "step": state.global_step,
            },
        }
        self._buffer.append(point)
        self._maybe_flush()

    def write_communication_metrics(self, task_code: str, metrics: dict[str, float]) -> None:
        """Queue a communication metric point."""
        point = {
            "measurement": "communication_metrics",
            "tags": {"task_code": task_code},
            "fields": metrics,
        }
        self._buffer.append(point)
        self._maybe_flush()

    def _maybe_flush(self) -> None:
        """Flush buffer if batch size or time interval exceeded."""
        now = time.time()
        if len(self._buffer) >= self.batch_size or (now - self._last_flush) >= self.flush_interval:
            self.flush()

    def flush(self) -> None:
        """Write all buffered points to InfluxDB."""
        if not self._buffer:
            return

        self._ensure_client()
        if self._write_api is None:
            # InfluxDB not available – clear buffer and skip
            self._buffer.clear()
            return

        try:
            from influxdb_client import Point

            points = []
            for record in self._buffer:
                p = Point(record["measurement"])
                for tag_key, tag_val in record.get("tags", {}).items():
                    p = p.tag(tag_key, str(tag_val))
                for field_key, field_val in record.get("fields", {}).items():
                    p = p.field(field_key, field_val)
                points.append(p)

            self._write_api.write(bucket=self.bucket, org=self.org, record=points)
        except Exception:
            pass  # Silently ignore write failures to not disrupt training
        finally:
            self._buffer.clear()
            self._last_flush = time.time()

    def close(self) -> None:
        """Flush remaining points and close the client."""
        self.flush()
        if self._client is not None:
            self._client.close()
            self._client = None
            self._write_api = None

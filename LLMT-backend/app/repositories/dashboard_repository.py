"""Dashboard repository — queries InfluxDB (metrics) and PostgreSQL (tasks/activities)."""

from collections.abc import Iterable
from datetime import datetime, timezone
import socket
import subprocess
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.database import get_influx_client, settings
from app.models.system_log import SystemLog
from app.models.training_task import TrainingTask


def _is_influx_reachable(url: str, timeout_ms: int) -> bool:
    """Fast preflight so dashboard endpoints do not block when InfluxDB is down."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    timeout = max(0.1, min(timeout_ms / 1000, 1.0))
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _get_dashboard_query_api():
    if not _is_influx_reachable(settings.INFLUXDB_URL, settings.INFLUXDB_TIMEOUT_MS):
        return None
    return get_influx_client().query_api()


def _extract_max_steps(config: dict) -> int | None:
    hyperparams = config.get("hyperparams", {})
    if isinstance(hyperparams, dict) and hyperparams.get("max_steps"):
        return int(hyperparams["max_steps"])
    if config.get("max_steps"):
        return int(config["max_steps"])
    return None


def _task_progress(task: TrainingTask) -> float:
    config = task.config_json or {}
    max_steps = _extract_max_steps(config)
    if max_steps and max_steps > 0:
        return min(task.current_step / max_steps * 100, 100)

    max_epoch = task.max_epoch or 0
    if max_epoch > 0 and task.current_epoch > 0:
        return min(task.current_epoch / max_epoch * 100, 100)

    if max_epoch > 0 and task.current_step > 0:
        return min(task.current_step / (max_epoch * 1000) * 100, 100)

    return 0.0


def _get_local_gpu_status() -> tuple[float, float, float]:
    """Return local GPU memory/utilization from nvidia-smi when InfluxDB has no point."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=1,
        )
    except Exception:
        return 0.0, 0.0, 0.0

    used = 0.0
    total = 0.0
    utilizations: list[float] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            used += float(parts[0])
            total += float(parts[1])
            utilizations.append(float(parts[2]))
        except ValueError:
            continue
    utilization = round(sum(utilizations) / len(utilizations), 2) if utilizations else 0.0
    return used, total, utilization


def get_summary(db: Session) -> dict:
    gpu_mem_used = 0.0
    gpu_mem_total = 0.0
    comm_latency = 0.0
    gpu_util = 0.0
    cpu_util = 0.0

    try:
        query_api = _get_dashboard_query_api()
        if query_api:
            result = query_api.query(
                f'from(bucket:"{settings.INFLUXDB_BUCKET}") '
                '|> range(start: -15m) '
                '|> filter(fn: (r) => r._measurement == "gpu_metrics") '
                '|> filter(fn: (r) => r._field == "memory_used_mb" or r._field == "memory_total_mb" or r._field == "utilization_pct") '
                '|> last()',
                org=settings.INFLUXDB_ORG,
            )
            for table in result:
                for record in table.records:
                    if record.get_field() == "memory_used_mb":
                        gpu_mem_used = float(record.get_value())
                    elif record.get_field() == "memory_total_mb":
                        gpu_mem_total = float(record.get_value())
                    elif record.get_field() == "utilization_pct":
                        gpu_util = float(record.get_value())
                    elif record.get_field() == "cpu_utilization":
                        cpu_util = float(record.get_value())
    except Exception:
        pass

    if gpu_mem_total <= 0:
        gpu_mem_used, gpu_mem_total, gpu_util = _get_local_gpu_status()

    try:
        query_api = _get_dashboard_query_api()
        if query_api:
            result = query_api.query(
                f'from(bucket:"{settings.INFLUXDB_BUCKET}") '
                '|> range(start: -15m) '
                '|> filter(fn: (r) => r._measurement == "communication_metrics") '
                '|> filter(fn: (r) => r._field == "all_reduce_latency_ms" or r._field == "all_gather_latency_ms" or r._field == "latency_ms") '
                '|> last()',
                org=settings.INFLUXDB_ORG,
            )
            values = [
                float(record.get_value())
                for table in result
                for record in table.records
                if record.get_value() is not None
            ]
            if values:
                comm_latency = round(sum(values) / len(values), 3)
    except Exception:
        pass

    running = db.query(TrainingTask).filter(TrainingTask.status == "running").count()
    paused = db.query(TrainingTask).filter(TrainingTask.status == "paused").count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_completed = db.query(TrainingTask).filter(
        TrainingTask.status == "completed",
        TrainingTask.ended_at >= today_start,
    ).count()
    alert_count = db.query(SystemLog).filter(
        SystemLog.action.in_(["security_alert", "error", "critical"]),
        SystemLog.created_at >= today_start,
    ).count()

    running_tasks = db.query(TrainingTask).filter(TrainingTask.status == "running").all()
    progress = 0.0
    if running_tasks:
        progress = round(sum(_task_progress(t) for t in running_tasks) / len(running_tasks), 1)

    return {
        "gpu_memory_used": gpu_mem_used,
        "gpu_memory_total": gpu_mem_total,
        "communication_latency_ms": comm_latency,
        "training_progress": progress,
        "running_tasks": running,
        "paused_tasks": paused,
        "today_completed": today_completed,
        "alert_count": alert_count,
        "gpu_utilization": gpu_util,
        "cpu_utilization": cpu_util,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _records_to_series(result: Iterable) -> list[dict]:
    series: list[dict] = []
    for table in result:
        for record in table.records:
            if record.get_value() is None:
                continue
            ts = record.get_time().isoformat() if record.get_time() else ""
            series.append({"timestamp": ts, "value": float(record.get_value())})
    return sorted(series, key=lambda item: item["timestamp"])


def _query_metric_series(query_api, range_str: str, measurement: str, fields: tuple[str, ...]) -> dict[str, list[dict]]:
    field_filter = " or ".join([f'r._field == "{field}"' for field in fields])
    result = query_api.query(
        f'from(bucket:"{settings.INFLUXDB_BUCKET}") '
        f'|> range(start: -{range_str}) '
        f'|> filter(fn: (r) => r._measurement == "{measurement}") '
        f'|> filter(fn: (r) => {field_filter}) '
        '|> aggregateWindow(every: 30s, fn: mean, createEmpty: false) '
        '|> group(columns: ["_field"]) '
        '|> sort(columns: ["_time"])',
        org=settings.INFLUXDB_ORG,
    )
    series = {field: [] for field in fields}
    for table in result:
        for record in table.records:
            field = record.get_field()
            if field not in series or record.get_value() is None:
                continue
            series[field].append({
                "timestamp": record.get_time().isoformat() if record.get_time() else "",
                "value": float(record.get_value()),
            })
    return series


def _gpu_memory_percent_series(gpu_metrics: dict[str, list[dict]]) -> list[dict]:
    used_by_time = {item["timestamp"]: item["value"] for item in gpu_metrics.get("memory_used_mb", [])}
    total_by_time = {item["timestamp"]: item["value"] for item in gpu_metrics.get("memory_total_mb", [])}
    timestamps = sorted(set(used_by_time) & set(total_by_time))
    series: list[dict] = []
    for timestamp in timestamps:
        total = total_by_time[timestamp]
        if total <= 0:
            continue
        series.append({
            "timestamp": timestamp,
            "value": round(min(100.0, used_by_time[timestamp] / total * 100), 2),
        })
    return series


def get_metrics(range_str: str = "1h") -> dict:
    """Return loss / accuracy / gpu / latency time-series from InfluxDB."""
    loss_series: list[dict] = []
    accuracy_series: list[dict] = []
    gpu_series: list[dict] = []
    gpu_memory_series: list[dict] = []
    lat_series: list[dict] = []

    try:
        query_api = _get_dashboard_query_api()
        if query_api:
            training = _query_metric_series(query_api, range_str, "training_step", ("loss", "accuracy"))
            gpu_metrics = _query_metric_series(
                query_api,
                range_str,
                "gpu_metrics",
                ("utilization_pct", "memory_used_mb", "memory_total_mb"),
            )
            communication = _query_metric_series(
                query_api,
                range_str,
                "communication_metrics",
                ("all_reduce_latency_ms", "all_gather_latency_ms", "latency_ms"),
            )
            loss_series = training["loss"]
            accuracy_series = training["accuracy"]
            gpu_series = gpu_metrics["utilization_pct"]
            gpu_memory_series = _gpu_memory_percent_series(gpu_metrics)
            lat_series = (
                communication["latency_ms"]
                or communication["all_reduce_latency_ms"]
                or communication["all_gather_latency_ms"]
            )
    except Exception:
        pass

    if not gpu_memory_series:
        used, total, utilization = _get_local_gpu_status()
        if total > 0:
            now = datetime.now(timezone.utc).isoformat()
            gpu_memory_series = [{"timestamp": now, "value": round(min(100.0, used / total * 100), 2)}]
            if not gpu_series:
                gpu_series = [{"timestamp": now, "value": utilization}]

    return {
        "loss": loss_series,
        "accuracy": accuracy_series,
        "gpu_utilization": gpu_series,
        "gpu_memory": gpu_memory_series,
        "latency": lat_series,
    }


def get_training_tasks(db: Session) -> list[dict]:
    tasks = (
        db.query(TrainingTask)
        .filter(TrainingTask.status.in_(["running", "paused"]))
        .order_by(TrainingTask.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "task_id": str(t.id),
            "task_name": t.task_name,
            "model": (t.config_json or {}).get("model_code", t.framework or "unknown"),
            "status": t.status,
            "progress": int(
                _task_progress(t)
            ),
            "current_epoch": t.current_epoch,
            "current_step": t.current_step,
            "max_epoch": t.max_epoch,
            "loss": (t.config_json or {}).get("loss"),
            "gpu": (t.config_json or {}).get("gpu_count", 1),
            "framework": t.framework,
            "parallel_strategy": t.parallel_strategy,
        }
        for t in tasks
    ]


def get_activities(db: Session, limit: int = 10) -> list[dict]:
    logs = (
        db.query(SystemLog)
        .order_by(SystemLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": lg.id,
            "username": lg.username,
            "action": lg.action,
            "resource": lg.resource,
            "detail": lg.detail,
            "created_at": lg.created_at.isoformat() if lg.created_at else "",
        }
        for lg in logs
    ]


def _alert_level(action: str, detail: str) -> str:
    """Map action/detail to alert severity level."""
    text = (action + " " + detail).lower()
    if any(k in text for k in ["critical", "fatal", "oom", "cuda error"]):
        return "critical"
    if any(k in text for k in ["error", "失败", "failed", "cve-", "overflow"]):
        return "warning"
    return "info"


def get_alerts(db: Session, limit: int = 10) -> list[dict]:
    logs = (
        db.query(SystemLog)
        .filter(
            SystemLog.action.in_(
                ["error", "ERROR", "critical", "CRITICAL", "alert", "ALERT",
                 "security_alert", "login_failed", "login_blocked"]
            )
        )
        .order_by(SystemLog.created_at.desc())
        .limit(limit)
        .all()
    )
    if not logs:
        logs = (
            db.query(SystemLog)
            .filter(SystemLog.action.in_(["error", "security_alert", "login_failed"]))
            .order_by(SystemLog.created_at.desc())
            .limit(3)
            .all()
        )
    return [
        {
            "level": _alert_level(lg.action, lg.detail),
            "message": lg.detail or lg.action,
            "source": lg.resource,
            "created_at": lg.created_at.isoformat() if lg.created_at else "",
        }
        for lg in logs
    ]

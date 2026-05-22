"""Dashboard repository — queries InfluxDB (metrics) and PostgreSQL (tasks/activities)."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import get_influx_client, settings
from app.models.system_log import SystemLog
from app.models.training_task import TrainingTask


def get_summary(db: Session) -> dict:
    gpu_mem_used = 32.0
    gpu_mem_total = 80.0
    comm_latency = 18.0
    gpu_util = 72.5
    cpu_util = 45.2

    try:
        client = get_influx_client()
        query_api = client.query_api()
        result = query_api.query(
            f'from(bucket:"{settings.INFLUXDB_BUCKET}") '
            '|> range(start: -1m) '
            '|> filter(fn: (r) => r._measurement == "gpu_metrics") '
            '|> last()'
        )
        for table in result:
            for record in table.records:
                if record.get_field() == "gpu_memory_used":
                    gpu_mem_used = float(record.get_value())
                elif record.get_field() == "gpu_memory_total":
                    gpu_mem_total = float(record.get_value())
                elif record.get_field() == "communication_latency_ms":
                    comm_latency = float(record.get_value())
                elif record.get_field() == "gpu_utilization":
                    gpu_util = float(record.get_value())
                elif record.get_field() == "cpu_utilization":
                    cpu_util = float(record.get_value())
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
        for t in running_tasks:
            ep = t.current_epoch or 0
            mx = t.max_epoch or 1
            progress += (ep / mx) if mx > 0 else 0
        progress = round((progress / len(running_tasks)) * 100, 1)

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


def get_metrics(range_str: str = "1h") -> dict:
    """Return loss / accuracy / gpu / latency time-series from InfluxDB or simulated."""
    loss_series: list[dict] = []
    accuracy_series: list[dict] = []
    gpu_series: list[dict] = []
    lat_series: list[dict] = []

    try:
        client = get_influx_client()
        query_api = client.query_api()
        result = query_api.query(
            f'from(bucket:"{settings.INFLUXDB_BUCKET}") '
            f'|> range(start: -{range_str}) '
            '|> filter(fn: (r) => r._measurement == "training_metrics")'
        )
        for table in result:
            for record in table.records:
                ts = record.get_time().isoformat() if record.get_time() else ""
                val = float(record.get_value()) if record.get_value() is not None else 0.0
                entry = {"timestamp": ts, "value": val}
                field = record.get_field()
                if field == "loss":
                    loss_series.append(entry)
                elif field == "accuracy":
                    accuracy_series.append(entry)
                elif field == "gpu_utilization":
                    gpu_series.append(entry)
                elif field == "latency":
                    lat_series.append(entry)
    except Exception:
        pass

    # InfluxDB 不可用时提供模拟数据
    if not loss_series:
        now = datetime.now(timezone.utc)
        import math
        for i in range(20):
            t = now.isoformat()
            loss_series.append({"timestamp": t, "value": round(2.5 - i * 0.1 + math.sin(i * 0.5) * 0.3, 4)})
            accuracy_series.append({"timestamp": t, "value": round(0.55 + i * 0.018, 4)})
            gpu_series.append({"timestamp": t, "value": 65 + (i % 5) * 5})
            lat_series.append({"timestamp": t, "value": 15 + (i % 3) * 3})

    return {
        "loss": loss_series,
        "accuracy": accuracy_series,
        "gpu_utilization": gpu_series,
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
                (t.current_epoch / t.max_epoch * 100) if t.max_epoch and t.max_epoch > 0 else 0
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

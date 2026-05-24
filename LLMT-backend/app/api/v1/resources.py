"""Resource monitoring endpoints."""

import logging
import os
import platform
import subprocess

from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(prefix="/resources", tags=["资源管理"])
logger = logging.getLogger(__name__)


def _query_gpus() -> list[dict]:
    """Query real GPU data via nvidia-smi, returning one dict per GPU."""
    query_fields = [
        "index",
        "name",
        "utilization.gpu",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
        "utilization.memory",
    ]
    query_str = ",".join(query_fields)
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query_str}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning("nvidia-smi failed: %s", result.stderr)
            return []
        gpus: list[dict] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            values = [v.strip() for v in line.split(",")]
            gpus.append({
                "index": int(values[0]),
                "name": values[1],
                "utilization_pct": int(values[2]) if values[2] else 0,
                "memory_used_mb": int(values[3]) if values[3] else 0,
                "memory_total_mb": int(values[4]) if values[4] else 0,
                "temperature_c": int(float(values[5])) if values[5] and values[5] != "[Not Supported]" else None,
                "power_w": int(float(values[6])) if values[6] and values[6] != "[Not Supported]" else None,
                "memory_utilization_pct": int(values[7]) if values[7] else 0,
            })
        return gpus
    except Exception as exc:
        logger.warning("GPU query failed: %s", exc)
        return []


def _count_gpu_processes(gpu_index: int) -> int:
    """Count processes running on a specific GPU."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return 0
        count = 0
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            count += 1
        # nvidia-smi --query-compute-apps doesn't filter by index easily,
        # so we approximate: count all processes and distribute evenly
        return count
    except Exception:
        return 0


@router.get("/gpu/status")
def get_gpu_status():
    gpu_list = _query_gpus()
    total_processes = sum(_count_gpu_processes(g["index"]) for g in gpu_list)

    if not gpu_list:
        return success_response({
            "nodes": [],
            "summary": {
                "total_gpus": 0,
                "used_gpus": 0,
                "available_gpus": 0,
                "total_memory_mb": 0,
                "used_memory_mb": 0,
            },
        })

    used_gpus = sum(1 for g in gpu_list if g["utilization_pct"] > 0)
    total_mem = sum(g["memory_total_mb"] for g in gpu_list)
    used_mem = sum(g["memory_used_mb"] for g in gpu_list)

    # Assign processes proportionally to utilized GPUs
    active_gpus = [g for g in gpu_list if g["utilization_pct"] > 0] or gpu_list
    for i, g in enumerate(gpu_list):
        g["processes"] = (total_processes // len(active_gpus)) if g in active_gpus else 0

    return success_response({
        "nodes": [{
            "node_id": platform.node() or os.uname().nodename,
            "hostname": platform.node() or os.uname().nodename,
            "gpus": gpu_list,
        }],
        "summary": {
            "total_gpus": len(gpu_list),
            "used_gpus": used_gpus,
            "available_gpus": len(gpu_list) - used_gpus,
            "total_memory_mb": total_mem,
            "used_memory_mb": used_mem,
        },
    })

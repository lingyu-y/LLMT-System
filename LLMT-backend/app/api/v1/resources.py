"""Resource monitoring endpoints."""

from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(prefix="/resources", tags=["资源管理"])


@router.get("/gpu/status")
def get_gpu_status():
    return success_response({
        "nodes": [
            {
                "node_id": "node-01",
                "hostname": "gpu-server-01",
                "gpus": [
                    {"index": 0, "name": "NVIDIA A100 80GB", "utilization_pct": 85, "memory_used_mb": 65000, "memory_total_mb": 81920, "temperature_c": 68, "power_w": 280, "processes": 3},
                    {"index": 1, "name": "NVIDIA A100 80GB", "utilization_pct": 72, "memory_used_mb": 52000, "memory_total_mb": 81920, "temperature_c": 65, "power_w": 260, "processes": 2},
                    {"index": 2, "name": "NVIDIA A100 80GB", "utilization_pct": 0,  "memory_used_mb": 0,     "memory_total_mb": 81920, "temperature_c": 42, "power_w": 45,  "processes": 0},
                    {"index": 3, "name": "NVIDIA A100 80GB", "utilization_pct": 0,  "memory_used_mb": 0,     "memory_total_mb": 81920, "temperature_c": 40, "power_w": 42,  "processes": 0},
                ],
            },
            {
                "node_id": "node-02",
                "hostname": "gpu-server-02",
                "gpus": [
                    {"index": 0, "name": "NVIDIA A100 80GB", "utilization_pct": 93, "memory_used_mb": 78000, "memory_total_mb": 81920, "temperature_c": 72, "power_w": 310, "processes": 4},
                    {"index": 1, "name": "NVIDIA A100 80GB", "utilization_pct": 0,  "memory_used_mb": 0,     "memory_total_mb": 81920, "temperature_c": 38, "power_w": 40,  "processes": 0},
                ],
            },
        ],
        "summary": {
            "total_gpus": 6,
            "used_gpus": 3,
            "available_gpus": 3,
            "total_memory_mb": 491520,
            "used_memory_mb": 195000,
        },
    })

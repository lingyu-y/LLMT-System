"""滑动窗口限流引擎 — Redis sorted set + 内存降级。"""

import time
import threading
from collections import defaultdict
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Redis 连接（惰性初始化）
# ---------------------------------------------------------------------------
_redis = None
_redis_available = False


def _get_redis():
    global _redis, _redis_available
    if _redis is not None:
        return _redis if _redis_available else None
    try:
        import redis
        settings = get_settings()
        _redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            db=2,  # separate DB from Celery
            socket_connect_timeout=1,
            decode_responses=True,
        )
        _redis.ping()
        _redis_available = True
    except Exception:
        _redis_available = False
        _redis = None
    return _redis if _redis_available else None


# ---------------------------------------------------------------------------
# 内存降级（单进程兜底）
# ---------------------------------------------------------------------------
_memory_store: dict[str, list[float]] = defaultdict(list)
_memory_lock = threading.Lock()
_memory_cleanup_at: float = 0.0


# ---------------------------------------------------------------------------
# 滑动窗口算法
# ---------------------------------------------------------------------------
def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int = 60,
) -> tuple[bool, dict]:
    """
    检查 key 在 window_seconds 内的请求是否超限。

    返回 (allowed, info)：
      allowed=True  → 请求通过
      allowed=False → 限流
    """
    now = time.time()
    window_start = now - window_seconds

    r = _get_redis()
    if r:
        return _check_redis(r, key, max_requests, window_seconds, now, window_start)
    else:
        return _check_memory(key, max_requests, window_seconds, now, window_start)


def _check_redis(r, key, max_requests, window_seconds, now, window_start):
    """Redis sorted set 滑动窗口。"""
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)  # 清理过期
    pipe.zcard(key)                                # 当前窗口内计数
    pipe.expire(key, window_seconds * 2)           # 设置 TTL
    _, current, _ = pipe.execute()

    allowed = current < max_requests
    if allowed:
        r.zadd(key, {f"{now}:{threading.get_ident()}": now})
        r.expire(key, window_seconds * 2)
        current += 1

    if not allowed:
        oldest = r.zrange(key, 0, 0, withscores=True)
        retry_after = int(oldest[0][1] + window_seconds - now) if oldest else window_seconds
    else:
        retry_after = 0

    return allowed, {
        "limit": max_requests,
        "remaining": max(0, max_requests - current),
        "current": current,
        "window_seconds": window_seconds,
        "retry_after_seconds": max(0, retry_after) if not allowed else 0,
    }


def _check_memory(key, max_requests, window_seconds, now, window_start):
    """内存滑动窗口（无 Redis 时降级）。"""
    global _memory_cleanup_at
    with _memory_lock:
        timestamps = _memory_store[key]
        # 清理过期
        timestamps = [t for t in timestamps if t > window_start]
        current = len(timestamps)
        allowed = current < max_requests

        if allowed:
            timestamps.append(now)
            _memory_store[key] = timestamps
            remaining = max(0, max_requests - current - 1)
        else:
            remaining = 0

        # 全局清理（每 60s 一次）
        if now - _memory_cleanup_at > 60:
            expired_keys = [k for k, v in _memory_store.items() if not v]
            for k in expired_keys:
                del _memory_store[k]
            _memory_cleanup_at = now

    retry_after = int(timestamps[0] + window_seconds - now) if not allowed and timestamps else 0
    return allowed, {
        "limit": max_requests,
        "remaining": remaining,
        "current": current + 1 if allowed else current,
        "window_seconds": window_seconds,
        "retry_after_seconds": max(0, retry_after) if not allowed else 0,
    }


# ---------------------------------------------------------------------------
# 标识提取
# ---------------------------------------------------------------------------
def extract_rate_limit_key(request: Request, user_id: int | None = None) -> str:
    """生成多维度限流 key：user_id + IP + X-API-Key 的前缀组合。"""
    ip = request.client.host if request.client else "unknown"
    api_key = request.headers.get("X-API-Key", "")
    user_part = f"user:{user_id}" if user_id else "user:anon"
    ip_part = f"ip:{ip}"
    key_part = f"key:{api_key[:12]}" if api_key else "key:none"
    return f"rate_limit:{user_part}:{ip_part}:{key_part}"


def extract_rate_limit_key_simple(request: Request) -> str:
    """按 IP 简单限流（无用户时）。"""
    ip = request.client.host if request.client else "unknown"
    return f"rate_limit:ip:{ip}"


# ---------------------------------------------------------------------------
# HTTP 429 响应
# ---------------------------------------------------------------------------
def rate_limit_exceeded_response(info: dict) -> JSONResponse:
    """构造 429 响应。"""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "请求频率超限，请稍后重试",
            "rate_limit": {
                "limit": info["limit"],
                "current": info["current"],
                "remaining": 0,
                "window_seconds": info["window_seconds"],
                "retry_after_seconds": info["retry_after_seconds"],
            },
        },
        headers={"Retry-After": str(info.get("retry_after_seconds", 60))},
    )


def rate_limit_http_exception(info: dict):
    """抛出 FastAPI HTTPException 429。"""
    from fastapi import HTTPException
    return HTTPException(
        status_code=429,
        detail={
            "detail": "请求频率超限，请稍后重试",
            "rate_limit": info,
        },
        headers={
            "Retry-After": str(info.get("retry_after_seconds", 60)),
            **rate_limit_headers(info),
        },
    )


def rate_limit_headers(info: dict) -> dict:
    """注入限流响应头（即使未超限也返回状态）。"""
    return {
        "X-RateLimit-Limit": str(info["limit"]),
        "X-RateLimit-Remaining": str(info["remaining"]),
        "X-RateLimit-Reset": str(int(time.time() + info["window_seconds"])),
    }

"""限流 FastAPI 依赖 — 按用户 + IP + API Key 多维度。"""

from fastapi import Depends, Request

from app.core.rate_limit import (
    check_rate_limit,
    extract_rate_limit_key,
    extract_rate_limit_key_simple,
    rate_limit_headers,
    rate_limit_exceeded_response,
)


def _get_rate_limit_response(request: Request, info: dict) -> dict:
    resp = rate_limit_exceeded_response(info)
    resp.headers.update(rate_limit_headers(info))
    # 注入额外 header
    for k, v in rate_limit_headers(info).items():
        resp.headers[k] = v
    return resp


class RateLimiter:
    """可配置的限流依赖，默认为 100次/60s/标识。"""

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60,
        per_user: bool = True,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.per_user = per_user

    async def __call__(self, request: Request):
        from fastapi import HTTPException

        user_id = None
        if self.per_user:
            # 尝试从 request.state 获取 user，若无则按 IP 限流
            user_id = getattr(request.state, "user_id", None)

        key = extract_rate_limit_key(request, user_id)
        allowed, info = check_rate_limit(key, self.max_requests, self.window_seconds)

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": "请求频率超限，请稍后重试",
                    "rate_limit": info,
                },
            )

        return info


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
):
    """工厂函数：按 IP 限流（无需用户登录）。"""
    limiter = RateLimiter(
        max_requests=max_requests,
        window_seconds=window_seconds,
        per_user=False,
    )
    return Depends(limiter)


def user_rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
):
    """工厂函数：按 用户+IP 多维度限流（需要 get_current_user 先执行）。"""
    limiter = RateLimiter(
        max_requests=max_requests,
        window_seconds=window_seconds,
        per_user=True,
    )
    return Depends(limiter)

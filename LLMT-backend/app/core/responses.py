"""Common response helpers."""

from typing import Any


def success_response(data: Any = None, message: str = "操作成功") -> dict:
    result: dict[str, Any] = {"message": message}
    if data is not None:
        result["data"] = data
    return result


def paginated_response(data: list[Any], total: int, page: int, page_size: int) -> dict:
    return {"data": data, "total": total, "page": page, "page_size": page_size}

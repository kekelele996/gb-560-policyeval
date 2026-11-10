"""通用响应结构：分页壳 + 序列化小工具。"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def paginated(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


def page_params(page: int | None = None, page_size: int | None = None) -> tuple[int, int]:
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 20)))
    return page, page_size

"""限流与每日配额中间件（Redis）。

两档限制，命中任一即抛 429：
1. 每用户每路由每分钟 RATE_LIMIT_PER_MINUTE 次（滑动窗口 ZSET）；
2. 每用户每自然日按角色配额（daemon 计数 INCR + 首键过期到次日）。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from fastapi import Depends, Request

from src.config.settings import settings
from src.constants import error_codes as codes
from src.middlewares.auth import get_current_user
from src.models.user import User
from src.utils.errors import AppError
from src.utils.redis_client import get_redis


def _window_check(key: str, limit: int, window_seconds: int = 60) -> None:
    now = time.time()
    client = get_redis()
    pipeline = client.pipeline()
    pipeline.zremrangebyscore(key, 0, now - window_seconds)
    pipeline.zadd(key, {f"{now}": now})
    pipeline.zcard(key)
    pipeline.expire(key, window_seconds)
    results = pipeline.execute()
    count = int(results[2])
    if count > limit:
        raise AppError(
            codes.RATE_LIMITED,
            "请求过于频繁，请稍后重试",
            f"key={key} count={count} limit={limit}",
            extra={"retry_after": window_seconds},
        )


def _daily_check(user: User, day_key: str) -> None:
    quota = settings.daily_quota_for(user.role)
    key = f"quota:daily:{user.id}:{day_key}"
    client = get_redis()
    count = int(client.incr(key))
    if count == 1:
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        ttl = max(60, int((tomorrow - now).total_seconds()))
        client.expire(key, ttl)
    if count > quota:
        raise AppError(
            codes.DAILY_QUOTA_EXCEEDED,
            f"已超出 {user.role} 角色的每日调用配额（{quota} 次）",
            f"key={key} count={count} quota={quota}",
            extra={"quota": quota, "used": count, "role": user.role},
        )


def rate_limit(bucket: str = "default"):
    """路由级限流依赖；bucket 只影响 key 命名。"""

    def dependency(request: Request, user: User = Depends(get_current_user)) -> None:
        try:
            day_key = datetime.now().strftime("%Y%m%d")
            if request.url.path.startswith("/api"):
                normalised = request.url.path
            else:
                normalised = "/api" + request.url.path
            _window_check(
                f"ratelimit:{bucket}:{user.id}:{normalised}",
                settings.RATE_LIMIT_PER_MINUTE,
            )
            _daily_check(user, day_key)
        except AppError:
            raise
        except Exception:
            # Redis 不可用时降级放行，避免基础设施抖动打断合规工作台
            return

    return Depends(dependency)

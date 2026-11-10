"""Redis 单例客户端（限流 / 每日配额 / worker 心跳）。"""
from __future__ import annotations

from functools import lru_cache

import redis

from src.config.settings import settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def redis_available() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False

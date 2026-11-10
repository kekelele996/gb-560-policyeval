"""worker 心跳（beat 每 20s）：写 Redis 时间戳供容器 healthcheck 判断。"""
from __future__ import annotations

import os
import time

import redis

from worker_src.config.celery_app import celery_app

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


@celery_app.task(name="policyeval.heartbeat")
def heartbeat() -> float:
    now = time.time()
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.set("policyeval:worker:heartbeat", f"{now:.3f}", ex=180)
    except Exception:
        pass
    return now

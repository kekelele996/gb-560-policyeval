"""worker 健康检查：Redis 心跳键（beat 每 20s 写一次），兜底 celery inspect ping。"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/backend")

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
HEARTBEAT_KEY = "policyeval:worker:heartbeat"


def heartbeat_ok() -> bool:
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        value = client.get(HEARTBEAT_KEY)
        if not value:
            return False
        return (time.time() - float(value)) < 90
    except Exception:
        return False


def celery_ok() -> bool:
    try:
        from worker_src.config.celery_app import celery_app

        replies = celery_app.control.ping(timeout=3)
        return bool(replies)
    except Exception:
        return False


if heartbeat_ok() or celery_ok():
    print("worker healthy")
    sys.exit(0)
print("worker unhealthy: no heartbeat and no celery pong")
sys.exit(1)

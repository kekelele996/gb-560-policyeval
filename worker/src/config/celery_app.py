"""worker 侧 Celery 应用：注册任务 + beat 心跳。"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "policyeval",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "worker_src.tasks.evaluate_task",
        "worker_src.tasks.heartbeat_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "worker-heartbeat": {"task": "policyeval.heartbeat", "schedule": 20.0},
    },
)

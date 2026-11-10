"""backend 侧 Celery 客户端：只投递任务，消费在 worker 容器。"""
from __future__ import annotations

from celery import Celery

from src.config.settings import settings

celery_app = Celery("policyeval", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
)

# 任务名：backend 投递 / worker 注册，跨容器靠字符串约定
TASK_EVALUATE_RUN = "policyeval.evaluate_run"

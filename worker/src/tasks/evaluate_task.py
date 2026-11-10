"""评估任务：backend 投递 policyeval.evaluate_run -> worker 真正执行算法。"""
from __future__ import annotations

from worker_src.config.celery_app import celery_app


@celery_app.task(name="policyeval.evaluate_run", bind=True, max_retries=1)
def evaluate_run(self, run_id: str) -> dict:
    from src.services.run_service import execute_run_by_id

    try:
        execute_run_by_id(run_id)
        return {"run_id": run_id, "status": "done"}
    except Exception as exc:  # noqa: BLE001
        # run_service 已把 failed 状态写库，这里只记录重试信息
        raise self.retry(exc=exc, countdown=3) if self.request.retries < 1 else {"run_id": run_id, "error": str(exc)}
    finally:
        import redis
        import os

        try:
            client = redis.Redis.from_url(
                os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
            )
            client.set("policyeval:worker:last_task", run_id)
        except Exception:
            pass

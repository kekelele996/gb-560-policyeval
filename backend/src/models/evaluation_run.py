from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base
from src.models.base import utcnow


class EvaluationRun(Base):
    """一次评估运行（worker 真实执行，前端轮询状态）。"""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_key: Mapped[str | None] = mapped_column(
        String(80), unique=True, nullable=True, index=True
    )
    bundle_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    rules_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    docs_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    violation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scope_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    include_quota: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    triggered_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

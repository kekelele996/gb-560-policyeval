from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base
from src.models.base import utcnow


class RemediationAdvice(Base):
    """整改建议：由 violation evidence 生成 patch_yaml + 影响面估算。"""

    __tablename__ = "remediation_advices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    violation_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    patch_yaml: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT, "mysql"), nullable=False, default=""
    )
    impact: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    effort_level: Mapped[str] = mapped_column(String(4), nullable=False, default="M")
    generated_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

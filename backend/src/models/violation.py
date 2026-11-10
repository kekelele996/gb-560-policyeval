from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base
from src.models.base import utcnow


class Violation(Base):
    """违规记录：DSL 求值或配额判定产生，evidence_json 存字段路径与实际值。"""

    __tablename__ = "violations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    policy_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="dsl")
    resource_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    resource_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    owner_team: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

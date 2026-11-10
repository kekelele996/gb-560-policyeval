from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base
from src.models.base import TimestampMixin, new_id


class AuditLog(Base, TimestampMixin):
    """关键动作审计：登录、导入、写策略、跑评估、审批豁免、生成建议。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    actor_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    actor_email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

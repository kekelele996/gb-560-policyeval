from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base
from src.models.base import utcnow


class Exemption(Base):
    """豁免申请：owner/engineer 发起，admin 审批；过期后需重新申请。"""

    __tablename__ = "exemptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    resource_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    approved_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

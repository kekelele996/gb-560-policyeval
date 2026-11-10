"""审计日志：写关键动作 + 管理员分页查询。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.models.audit_log import AuditLog
from src.models.user import User


def record(
    db: Session,
    *,
    action: str,
    entity_type: str = "",
    entity_id: str = "",
    actor: User | None = None,
    actor_id: str = "",
    actor_email: str = "",
    payload: dict[str, Any] | None = None,
    ip: str = "",
    trace_id: str = "",
    detail: str = "",
) -> AuditLog:
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor_id=str(actor.id) if actor else actor_id,
        actor_email=actor.email if actor else actor_email,
        payload=payload or {},
        ip=ip,
        trace_id=trace_id,
        detail=detail,
    )
    db.add(entry)
    db.flush()
    return entry


def list_logs(
    db: Session,
    *,
    action: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    total = query.count()
    items = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def serialize(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "actor_id": entry.actor_id,
        "actor_email": entry.actor_email,
        "payload": entry.payload or {},
        "ip": entry.ip,
        "trace_id": entry.trace_id,
        "detail": entry.detail,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }

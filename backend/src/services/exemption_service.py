"""豁免服务：申请 -> admin 审批 -> 评估时自动把命中违规标为 exception。

过期口径：approved 且 expires_at < now -> expired，并把对应违规恢复 open。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import ExemptionStatus
from src.models.base import new_id, utcnow
from src.models.exemption import Exemption
from src.models.policy_rule import PolicyRule
from src.models.user import User
from src.models.violation import Violation
from src.schemas.governance import ExemptionCreateRequest
from src.utils.errors import AppError

DEFAULT_EXEMPTION_DAYS = 90


def find_effective_exemption(
    db: Session, policy_id: str | None, namespace: str, resource_name: str
) -> Exemption | None:
    if not policy_id:
        return None
    now = utcnow()
    query = (
        db.query(Exemption)
        .filter(Exemption.policy_id == policy_id)
        .filter(Exemption.namespace == namespace)
        .filter(Exemption.resource_name == resource_name)
        .filter(Exemption.status == ExemptionStatus.APPROVED)
    )
    for item in query.all():
        if item.expires_at is None or item.expires_at >= now:
            return item
    return None


def request_exemption(
    db: Session, payload: ExemptionCreateRequest, user: User
) -> Exemption:
    violation = db.get(Violation, payload.violation_id)
    if violation is None:
        raise AppError(codes.NOT_FOUND, "违规记录不存在", payload.violation_id)
    from src.middlewares.auth import enforce_namespace_scope

    enforce_namespace_scope(user, violation.namespace)
    if not violation.policy_id:
        raise AppError(
            codes.VALIDATION_ERROR,
            "配额引擎产生的违规不支持豁免（应调整资源规约或由平台审批配额）",
            f"rule_code={violation.rule_code}",
        )
    existing = (
        db.query(Exemption)
        .filter(Exemption.policy_id == violation.policy_id)
        .filter(Exemption.namespace == violation.namespace)
        .filter(Exemption.resource_name == violation.resource_name)
        .filter(Exemption.status.in_([ExemptionStatus.PENDING, ExemptionStatus.APPROVED]))
        .first()
    )
    if existing is not None:
        raise AppError(
            codes.CONFLICT,
            "该违规已存在待审批或已通过的豁免",
            f"exemption_id={existing.id}",
            extra={"exemption_id": str(existing.id), "status": existing.status},
        )
    expires_at = payload.expires_at or (utcnow() + timedelta(days=DEFAULT_EXEMPTION_DAYS))
    exemption = Exemption(
        id=new_id(),
        policy_id=violation.policy_id,
        namespace=violation.namespace,
        resource_name=violation.resource_name,
        reason=payload.reason,
        requested_by=user.email,
        status=ExemptionStatus.PENDING,
        expires_at=expires_at,
        created_at=utcnow(),
    )
    db.add(exemption)
    db.flush()
    return exemption


def decide(
    db: Session, exemption: Exemption, decision: str, note: str, user: User
) -> Exemption:
    if exemption.status != ExemptionStatus.PENDING:
        raise AppError(
            codes.EXEMPTION_STATE,
            "只有待审批的豁免可以审批",
            f"status={exemption.status}",
        )
    if decision == "approve":
        exemption.status = ExemptionStatus.APPROVED
        exemption.approved_by = user.email
        exemption.decided_at = utcnow()
        exemption.decision_note = note
        _apply_approval(db, exemption)
    else:
        exemption.status = ExemptionStatus.REJECTED
        exemption.approved_by = user.email
        exemption.decided_at = utcnow()
        exemption.decision_note = note
    db.flush()
    return exemption


def _apply_approval(db: Session, exemption: Exemption) -> None:
    violations = (
        db.query(Violation)
        .filter(Violation.policy_id == exemption.policy_id)
        .filter(Violation.namespace == exemption.namespace)
        .filter(Violation.resource_name == exemption.resource_name)
        .filter(Violation.status == "open")
        .all()
    )
    for violation in violations:
        violation.status = "exception"
    db.flush()


def expire_overdue(db: Session) -> int:
    now = utcnow()
    expired = (
        db.query(Exemption)
        .filter(Exemption.status == ExemptionStatus.APPROVED)
        .filter(Exemption.expires_at.isnot(None))
        .filter(Exemption.expires_at < now)
        .all()
    )
    for item in expired:
        item.status = ExemptionStatus.EXPIRED
        violations = (
            db.query(Violation)
            .filter(Violation.policy_id == item.policy_id)
            .filter(Violation.namespace == item.namespace)
            .filter(Violation.resource_name == item.resource_name)
            .filter(Violation.status == "exception")
            .all()
        )
        for violation in violations:
            violation.status = "open"
    if expired:
        db.flush()
    return len(expired)


def list_exemptions(
    db: Session,
    *,
    user: User | None = None,
    status: str | None = None,
    namespace: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Exemption, PolicyRule | None]], int]:
    query = db.query(Exemption)
    if user is not None and user.role == "owner" and user.scope_namespaces:
        query = query.filter(Exemption.namespace.in_(user.scope_namespaces))
    if status:
        query = query.filter(Exemption.status == status)
    if namespace:
        query = query.filter(Exemption.namespace == namespace)
    total = query.count()
    rows = query.order_by(Exemption.created_at.desc()).offset(offset).limit(limit).all()
    policies = {
        str(p.id): p
        for p in db.query(PolicyRule).filter(PolicyRule.id.in_([r.policy_id for r in rows])).all()
    } if rows else {}
    return [(row, policies.get(str(row.policy_id))) for row in rows], total


def get_exemption(db: Session, exemption_id: str) -> Exemption:
    exemption = db.get(Exemption, exemption_id)
    if exemption is None:
        raise AppError(codes.NOT_FOUND, "豁免记录不存在", exemption_id)
    return exemption


def summary(db: Session, user: User | None = None) -> dict[str, Any]:
    query = db.query(Exemption)
    if user is not None and user.role == "owner" and user.scope_namespaces:
        query = query.filter(Exemption.namespace.in_(user.scope_namespaces))
    rows = query.all()
    counts = {status: 0 for status in ExemptionStatus.ALL}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {"total": len(rows), "by_status": counts}

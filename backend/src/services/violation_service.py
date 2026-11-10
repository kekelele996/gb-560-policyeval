"""违规服务：分页查询、namespace 聚合、evidence 详情、状态流转。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import QUOTA_RULE_CODE_OVER, QUOTA_RULE_CODE_REQ_GT_LIMIT
from src.middlewares.auth import enforce_namespace_scope
from src.models.exemption import Exemption
from src.models.policy_rule import PolicyRule
from src.models.remediation_advice import RemediationAdvice
from src.models.user import User
from src.models.violation import Violation
from src.utils.errors import AppError

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _scoped_query(db: Session, user: User):
    query = db.query(Violation)
    if user.role == "owner" and user.scope_namespaces:
        query = query.filter(Violation.namespace.in_(user.scope_namespaces))
    return query


def list_violations(
    db: Session,
    *,
    user: User,
    run_id: str | None = None,
    severity: str | None = None,
    namespace: str | None = None,
    status: str | None = None,
    source: str | None = None,
    policy_id: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Violation], int]:
    query = _scoped_query(db, user)
    if run_id:
        query = query.filter(Violation.run_id == run_id)
    if severity:
        query = query.filter(Violation.severity == severity)
    if namespace:
        query = query.filter(Violation.namespace == namespace)
    if status:
        query = query.filter(Violation.status == status)
    if source:
        query = query.filter(Violation.source == source)
    if policy_id:
        query = query.filter(Violation.policy_id == policy_id)
    if keyword:
        query = query.filter(Violation.resource_name.contains(keyword))
    total = query.count()
    rows = (
        query.order_by(Violation.severity.asc(), Violation.namespace.asc(), Violation.resource_name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # 严重度排序：critical 在前（字符串排序不满足，Python 侧稳定重排）
    rows.sort(key=lambda item: (-SEVERITY_RANK.get(item.severity, 0), item.namespace, item.resource_name))
    return rows, total


def summary(db: Session, *, user: User, run_id: str | None = None) -> dict[str, Any]:
    base = _scoped_query(db, user)
    if run_id:
        base = base.filter(Violation.run_id == run_id)
    rows = base.all()
    severity_counts = {key: 0 for key in ("critical", "high", "medium", "low")}
    status_counts = {"open": 0, "exception": 0, "fixed": 0}
    source_counts = {"dsl": 0, "quota": 0}
    namespaces: dict[str, dict[str, Any]] = {}
    policies: dict[str, dict[str, Any]] = {}
    quota_hotspots: list[dict[str, Any]] = []
    for row in rows:
        severity_counts[row.severity] = severity_counts.get(row.severity, 0) + 1
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        source_counts[row.source] = source_counts.get(row.source, 0) + 1
        bucket = namespaces.setdefault(
            row.namespace,
            {"namespace": row.namespace, "total": 0, "open": 0, "exception": 0, "fixed": 0},
        )
        bucket["total"] += 1
        bucket[row.status] = bucket.get(row.status, 0) + 1
        policy_key = row.rule_code
        policy_bucket = policies.setdefault(
            policy_key,
            {"rule_code": policy_key, "policy_id": row.policy_id, "total": 0, "open": 0, "severity": row.severity},
        )
        policy_bucket["total"] += 1
        if row.status == "open":
            policy_bucket["open"] += 1
        if row.source == "quota" and row.rule_code == QUOTA_RULE_CODE_OVER:
            evidence = row.evidence_json or {}
            quota_hotspots.append(
                {
                    "namespace": row.namespace,
                    "metric": evidence.get("metric"),
                    "used": evidence.get("used"),
                    "threshold": evidence.get("threshold"),
                    "threshold_source": evidence.get("threshold_source"),
                    "over_pct": evidence.get("over_pct"),
                    "ratio": evidence.get("ratio"),
                    "severity": row.severity,
                    "violation_id": str(row.id),
                }
            )
    quota_hotspots.sort(key=lambda item: item.get("over_pct") or 0, reverse=True)
    return {
        "run_id": run_id,
        "total": len(rows),
        "severity_counts": severity_counts,
        "status_counts": status_counts,
        "source_counts": source_counts,
        "namespaces": sorted(namespaces.values(), key=lambda item: item["total"], reverse=True),
        "policies": sorted(policies.values(), key=lambda item: item["total"], reverse=True),
        "quota_hotspots": quota_hotspots[:10],
        "open_total": status_counts.get("open", 0),
    }


def get_violation(db: Session, violation_id: str, user: User) -> Violation:
    violation = db.get(Violation, violation_id)
    if violation is None:
        raise AppError(codes.NOT_FOUND, "违规记录不存在", violation_id)
    enforce_namespace_scope(user, violation.namespace)
    return violation


def detail(db: Session, violation: Violation) -> dict[str, Any]:
    from src.schemas.evaluation import serialize_advice, serialize_violation

    payload = serialize_violation(violation, include_evidence=True)
    policy = db.get(PolicyRule, violation.policy_id) if violation.policy_id else None
    payload["policy"] = (
        {
            "id": str(policy.id),
            "code": policy.code,
            "title": policy.title,
            "severity": policy.severity,
            "kind": policy.kind,
            "dsl_text": policy.dsl_text,
        }
        if policy
        else None
    )
    advice = (
        db.query(RemediationAdvice)
        .filter(RemediationAdvice.violation_id == str(violation.id))
        .one_or_none()
    )
    payload["advice"] = serialize_advice(advice) if advice else None
    exemption = None
    if violation.policy_id:
        exemption = (
            db.query(Exemption)
            .filter(Exemption.policy_id == violation.policy_id)
            .filter(Exemption.namespace == violation.namespace)
            .filter(Exemption.resource_name == violation.resource_name)
            .order_by(Exemption.created_at.desc())
            .first()
        )
    payload["exemption"] = (
        {
            "id": str(exemption.id),
            "status": exemption.status,
            "reason": exemption.reason,
            "requested_by": exemption.requested_by,
            "expires_at": exemption.expires_at.isoformat() if exemption.expires_at else None,
        }
        if exemption
        else None
    )
    return payload


def update_status(
    db: Session, violation: Violation, new_status: str, note: str, user: User
) -> Violation:
    if new_status not in ("open", "fixed"):
        raise AppError(
            codes.VALIDATION_ERROR,
            "状态只能改为 open/fixed；exception 只能通过豁免审批产生",
            f"status={new_status}",
        )
    enforce_namespace_scope(user, violation.namespace)
    if violation.status == new_status:
        return violation
    if violation.source == "quota" and new_status == "fixed":
        # 配额违规的"修复"需要重新跑评估复核；此处只做状态标记，复核由重跑覆盖
        pass
    violation.status = new_status
    db.flush()
    return violation


def policy_options(db: Session) -> list[dict[str, Any]]:
    rows = db.query(PolicyRule).order_by(PolicyRule.code.asc()).all()
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "title": row.title,
            "severity": row.severity,
            "enabled": row.enabled,
        }
        for row in rows
    ]

"""系统路由：健康检查、工作台汇总、审计日志。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config.database import get_db, ping_db
from src.constants.enums import SEVERITY_LABELS
from src.middlewares.auth import get_current_user
from src.middlewares.rbac import require
from src.models.audit_log import AuditLog
from src.models.evaluation_run import EvaluationRun
from src.models.exemption import Exemption
from src.models.manifest_bundle import ManifestBundle
from src.models.policy_rule import PolicyRule
from src.models.user import User
from src.models.violation import Violation
from src.services import audit_service
from src.utils.redis_client import redis_available

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "policyeval-backend",
        "db": ping_db(),
        "redis": redis_available(),
    }


@router.get("/meta/summary")
def meta_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    bundle = db.query(ManifestBundle).order_by(ManifestBundle.imported_at.desc()).first()
    policy_total = db.query(func.count(PolicyRule.id)).scalar() or 0
    policy_enabled = (
        db.query(func.count(PolicyRule.id)).filter(PolicyRule.enabled.is_(True)).scalar() or 0
    )
    policy_broken = (
        db.query(func.count(PolicyRule.id))
        .filter(PolicyRule.parse_error_json.isnot(None))
        .scalar()
        or 0
    )
    run_total = db.query(func.count(EvaluationRun.id)).scalar() or 0
    latest_run = (
        db.query(EvaluationRun).order_by(EvaluationRun.started_at.desc()).first()
    )
    latest_done = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.status == "done")
        .order_by(EvaluationRun.started_at.desc())
        .first()
    )
    scoped = db.query(Violation)
    # 待整改计数只统计「最近一次已完成评估」，避免历史运行重复计数
    if latest_done is not None:
        scoped = scoped.filter(Violation.run_id == str(latest_done.id))
    if user.role == "owner" and user.scope_namespaces:
        scoped = scoped.filter(Violation.namespace.in_(user.scope_namespaces))
    severity_rows = (
        scoped.with_entities(Violation.severity, func.count(Violation.id))
        .filter(Violation.status == "open")
        .group_by(Violation.severity)
        .all()
    )
    severity_counts = {key: 0 for key in SEVERITY_LABELS}
    for severity, count in severity_rows:
        severity_counts[severity] = count
    namespace_rows = (
        scoped.with_entities(Violation.namespace, func.count(Violation.id))
        .filter(Violation.status == "open")
        .group_by(Violation.namespace)
        .order_by(func.count(Violation.id).desc())
        .limit(20)
        .all()
    )
    pending_exemptions = (
        db.query(func.count(Exemption.id)).filter(Exemption.status == "pending").scalar() or 0
    )
    approved_exemptions = (
        db.query(func.count(Exemption.id)).filter(Exemption.status == "approved").scalar() or 0
    )
    tree = (bundle.parsed_tree or []) if bundle else []
    namespaces = sorted({item["namespace"] for item in tree if item.get("namespace")})
    return {
        "customer": "澜川银行 · 云原生平台部",
        "bundle": {
            "id": str(bundle.id) if bundle else None,
            "name": bundle.name if bundle else None,
            "doc_count": bundle.doc_count if bundle else 0,
            "file_count": bundle.file_count if bundle else 0,
            "namespace_count": bundle.namespace_count if bundle else 0,
            "cluster": bundle.cluster if bundle else "",
        },
        "namespaces": namespaces,
        "policies": {"total": policy_total, "enabled": policy_enabled, "broken": policy_broken},
        "runs": {
            "total": run_total,
            "latest": (
                {
                    "id": str(latest_run.id),
                    "status": latest_run.status,
                    "violation_count": latest_run.violation_count,
                    "rules_evaluated": latest_run.rules_evaluated,
                    "rules_passed": latest_run.rules_passed,
                    "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
                }
                if latest_run
                else None
            ),
        },
        "open_violations": {
            "total": sum(severity_counts.values()),
            "severity": severity_counts,
            "by_namespace": [
                {"namespace": namespace, "count": count} for namespace, count in namespace_rows
            ],
        },
        "exemptions": {"pending": pending_exemptions, "approved": approved_exemptions},
        "role": user.role,
    }


@router.get("/audit")
def list_audit(
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require("audit:read")),
) -> dict:
    rows, total = audit_service.list_logs(db, action=action, limit=limit, offset=offset)
    return {
        "items": [audit_service.serialize(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

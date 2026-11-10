"""评估运行 / 违规 / 整改建议 controller。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.models.policy_rule import PolicyRule
from src.models.user import User
from src.schemas.common import page_params, paginated
from src.schemas.evaluation import (
    RemediationRequest,
    RunCreateRequest,
    ViolationStatusRequest,
    serialize_advice,
    serialize_run,
    serialize_violation,
)
from src.services import (
    audit_service,
    policy_service,
    remediation_service,
    run_service,
    violation_service,
)


def list_runs(db: Session, page: int | None, page_size: int | None) -> dict:
    page, page_size = page_params(page, page_size)
    rows, total = run_service.list_runs(db, limit=page_size, offset=(page - 1) * page_size)
    return paginated([serialize_run(row) for row in rows], total, page, page_size)


def create_run(request: Request, payload: RunCreateRequest, db: Session, user: User) -> dict:
    run = run_service.create_run(
        db,
        bundle_id=payload.bundle_id,
        policy_ids=payload.policy_ids,
        include_quota=True,
        user=user,
    )
    audit_service.record(
        db,
        action="runs.create",
        entity_type="EvaluationRun",
        entity_id=str(run.id),
        actor=user,
        payload={"bundle_id": str(run.bundle_id), "rules": len(run.scope_json or [])},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"run": serialize_run(run), "detail": run_service.run_detail(db, run)}


def get_run(db: Session, run_id: str) -> dict:
    run = run_service.get_run(db, run_id)
    return {
        "run": serialize_run(run, detail=True),
        "detail": run_service.run_detail(db, run),
    }


def retry_run(request: Request, run_id: str, db: Session, user: User) -> dict:
    run = run_service.get_run(db, run_id)
    run = run_service.retry_run(db, run, user)
    audit_service.record(
        db,
        action="runs.retry",
        entity_type="EvaluationRun",
        entity_id=str(run.id),
        actor=user,
        payload={"status": run.status},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"run": serialize_run(run)}


def execute_run(request: Request, run_id: str, db: Session, user: User) -> dict:
    """卡在 running 的运行可手动触发一次同步执行（worker 异常时的兜底）。"""
    run = run_service.get_run(db, run_id)
    if run.status == "done":
        return {"run": serialize_run(run), "detail": run_service.run_detail(db, run)}
    result = run_service.execute_run(db, run)
    audit_service.record(
        db,
        action="runs.execute_inline",
        entity_type="EvaluationRun",
        entity_id=str(run.id),
        actor=user,
        payload={"status": run.status, "result": {k: v for k, v in result.items() if k in ("elapsed_ms", "error")}},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {
        "run": serialize_run(run, detail=True),
        "detail": run_service.run_detail(db, run),
        "result": {key: value for key, value in result.items() if key != "quota_summary"},
    }


def _policy_map(db: Session, rows) -> dict[str, PolicyRule]:
    ids = {row.policy_id for row in rows if row.policy_id}
    if not ids:
        return {}
    return {
        str(policy.id): policy
        for policy in db.query(PolicyRule).filter(PolicyRule.id.in_(ids)).all()
    }


def list_violations(
    db: Session,
    user: User,
    *,
    page: int | None,
    page_size: int | None,
    run_id: str | None,
    severity: str | None,
    namespace: str | None,
    status: str | None,
    source: str | None,
    policy_id: str | None,
    keyword: str | None,
) -> dict:
    page, page_size = page_params(page, page_size)
    rows, total = violation_service.list_violations(
        db,
        user=user,
        run_id=run_id,
        severity=severity,
        namespace=namespace,
        status=status,
        source=source,
        policy_id=policy_id,
        keyword=keyword,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    policies = _policy_map(db, rows)
    items = []
    for row in rows:
        payload = serialize_violation(row)
        policy = policies.get(str(row.policy_id)) if row.policy_id else None
        payload["policy_code"] = policy.code if policy else row.rule_code
        payload["policy_title"] = policy.title if policy else "资源规约聚合与配额判定"
        items.append(payload)
    return paginated(items, total, page, page_size)


def violation_summary(db: Session, user: User, run_id: str | None) -> dict:
    return violation_service.summary(db, user=user, run_id=run_id)


def get_violation(db: Session, user: User, violation_id: str) -> dict:
    violation = violation_service.get_violation(db, violation_id, user)
    return {"violation": violation_service.detail(db, violation)}


def update_violation_status(
    request: Request,
    db: Session,
    user: User,
    violation_id: str,
    payload: ViolationStatusRequest,
) -> dict:
    violation = violation_service.get_violation(db, violation_id, user)
    violation = violation_service.update_status(db, violation, payload.status, payload.note, user)
    audit_service.record(
        db,
        action="violations.update_status",
        entity_type="Violation",
        entity_id=str(violation.id),
        actor=user,
        payload={"status": violation.status, "note": payload.note, "namespace": violation.namespace},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"violation": violation_service.detail(db, violation)}


def generate_remediation(
    request: Request,
    db: Session,
    user: User,
    violation_id: str,
    payload: RemediationRequest,
) -> dict:
    violation = violation_service.get_violation(db, violation_id, user)
    advice = remediation_service.generate(db, violation, user)
    audit_service.record(
        db,
        action="violations.generate_remediation",
        entity_type="Violation",
        entity_id=str(violation.id),
        actor=user,
        payload={"rule_code": violation.rule_code, "effort": advice.effort_level},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"advice": serialize_advice(advice)}


def get_remediation(db: Session, user: User, violation_id: str) -> dict:
    violation = violation_service.get_violation(db, violation_id, user)
    advice = remediation_service.get_advice(db, str(violation.id))
    return {"advice": serialize_advice(advice) if advice else None}


def policy_options(db: Session) -> dict:
    return {"items": violation_service.policy_options(db)}

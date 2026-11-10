"""策略服务：DSL 校验/入库/更新/试运行。解析失败保存行列诊断。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import PolicySeverity, RuleKind
from src.models.base import new_id
from src.models.policy_rule import PolicyRule
from src.models.user import User
from src.services import audit_service, bundle_service
from src.services.dsl_eval import dry_run_policy
from src.services.dsl_parser import DslParseError, parse_dsl
from src.schemas.catalog import PolicyCreateRequest, PolicyUpdateRequest
from src.utils.errors import AppError


def validate_dsl(dsl_text: str) -> dict[str, Any]:
    """校验入口：成功返回 ast 统计，失败返回带行列的 error（不抛异常）。"""
    try:
        parsed = parse_dsl(dsl_text)
    except DslParseError as exc:
        return {"ok": False, "error": exc.to_dict()}
    return {
        "ok": True,
        "error": None,
        "predicate_count": parsed["predicate_count"],
        "path_count": parsed["path_count"],
        "max_depth": parsed["max_depth"],
        "summary": parsed["summary"],
        "ast": parsed["ast"],
    }


def _parse_or_raise(dsl_text: str) -> dict[str, Any]:
    try:
        return parse_dsl(dsl_text)
    except DslParseError as exc:
        raise AppError(
            codes.DSL_PARSE_ERROR,
            "策略 DSL 解析失败",
            exc.message,
            extra={"error": exc.to_dict()},
        ) from exc


def create_policy(db: Session, payload: PolicyCreateRequest, user: User) -> PolicyRule:
    payload.validate_enums()
    if db.query(PolicyRule).filter(PolicyRule.code == payload.code).one_or_none():
        raise AppError(codes.CONFLICT, "策略编码已存在", f"code={payload.code}")
    parsed = _parse_or_raise(payload.dsl_text)
    policy = PolicyRule(
        id=new_id(),
        code=payload.code,
        title=payload.title,
        severity=payload.severity,
        kind=payload.kind,
        dsl_text=payload.dsl_text,
        ast_json=parsed,
        parse_error_json=None,
        enabled=payload.enabled,
        version=1,
        description=payload.description,
        created_by=user.email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(policy)
    db.flush()
    return policy


def update_policy(db: Session, policy: PolicyRule, payload: PolicyUpdateRequest, user: User) -> PolicyRule:
    changed: list[str] = []
    if payload.severity is not None:
        if payload.severity not in PolicySeverity.ALL:
            raise AppError(codes.VALIDATION_ERROR, f"severity 必须是 {PolicySeverity.ALL}")
        policy.severity = payload.severity
        changed.append("severity")
    if payload.kind is not None:
        if payload.kind not in RuleKind.ALL:
            raise AppError(codes.VALIDATION_ERROR, f"kind 必须是 {RuleKind.ALL}")
        policy.kind = payload.kind
        changed.append("kind")
    if payload.title is not None:
        policy.title = payload.title
        changed.append("title")
    if payload.description is not None:
        policy.description = payload.description
        changed.append("description")
    if payload.dsl_text is not None and payload.dsl_text != policy.dsl_text:
        parsed = _parse_or_raise(payload.dsl_text)
        policy.dsl_text = payload.dsl_text
        policy.ast_json = parsed
        policy.parse_error_json = None
        policy.version = (policy.version or 1) + 1
        changed.append("dsl_text")
    if payload.enabled is not None:
        policy.enabled = payload.enabled
        changed.append("enabled")
    policy.updated_at = datetime.utcnow()
    db.flush()
    return policy


def seed_policy(db: Session, spec: dict[str, Any]) -> tuple[PolicyRule, bool]:
    """seed：按 code 幂等创建；允许预置解析失败样本（parse_error 直接落库）。"""
    existing = db.query(PolicyRule).filter(PolicyRule.code == spec["code"]).one_or_none()
    if existing is not None:
        return existing, False
    parsed: dict[str, Any] | None = None
    parse_error: dict[str, Any] | None = None
    try:
        parsed = parse_dsl(spec["dsl_text"])
    except DslParseError as exc:
        parse_error = exc.to_dict()
        if not spec.get("broken"):
            raise
    policy = PolicyRule(
        id=new_id(),
        code=spec["code"],
        title=spec["title"],
        severity=spec["severity"],
        kind=spec["kind"],
        dsl_text=spec["dsl_text"],
        ast_json=parsed,
        parse_error_json=parse_error,
        enabled=spec.get("enabled", True),
        version=1,
        description=spec.get("description", ""),
        created_by=spec.get("created_by", "seed"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(policy)
    db.flush()
    return policy, True


def list_policies(db: Session, *, enabled: bool | None = None) -> list[PolicyRule]:
    query = db.query(PolicyRule)
    if enabled is not None:
        query = query.filter(PolicyRule.enabled.is_(enabled))
    return query.order_by(PolicyRule.code.asc()).all()


def get_policy(db: Session, policy_id: str) -> PolicyRule:
    policy = db.get(PolicyRule, policy_id)
    if policy is None:
        raise AppError(codes.NOT_FOUND, "策略不存在", f"policy_id={policy_id}")
    return policy


def enabled_policies(db: Session, policy_ids: list[str] | None = None) -> list[PolicyRule]:
    query = db.query(PolicyRule).filter(PolicyRule.enabled.is_(True))
    if policy_ids:
        query = query.filter(PolicyRule.id.in_(policy_ids))
    return query.order_by(PolicyRule.code.asc()).all()


def dry_run(db: Session, policy: PolicyRule, bundle_id: str) -> dict[str, Any]:
    if not policy.ast_json:
        raise AppError(
            codes.DSL_PARSE_ERROR,
            "策略 DSL 未通过解析，不能试运行",
            f"policy={policy.code}",
            extra={"error": policy.parse_error_json},
        )
    bundle = bundle_service.get_bundle(db, bundle_id)
    docs = bundle_service.load_docs(bundle)
    policy_dict = {
        "id": str(policy.id),
        "code": policy.code,
        "title": policy.title,
        "severity": policy.severity,
        "kind": policy.kind,
        "dsl_text": policy.dsl_text,
        "ast_json": policy.ast_json,
        "summary": (policy.ast_json or {}).get("summary"),
    }
    result = dry_run_policy(policy_dict, docs)
    result["bundle_id"] = str(bundle.id)
    result["bundle_name"] = bundle.name
    return result

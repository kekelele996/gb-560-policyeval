"""评估运行服务：创建运行 -> Celery 派发 -> worker 真实求值 -> 落库违规。

执行口径（两种算法同一运行里合并）：
- DSL 引擎：对每个启用的 PolicyRule 在 bundle 文档上求值（dsl_eval）。
- 配额引擎：对 bundle 全量文档跑资源规约聚合/配额判定（quota）。
rules_evaluated = 启用的 DSL 策略数 + 配额引擎 1 项；rules_passed = 命中 0 违规的规则数。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.config.celery_app import TASK_EVALUATE_RUN, celery_app
from src.config.database import session_scope
from src.constants import error_codes as codes
from src.constants.enums import QUOTA_RULE_CODE_OVER, QUOTA_RULE_CODE_REQ_GT_LIMIT, RunStatus
from src.models.base import new_id, utcnow
from src.models.evaluation_run import EvaluationRun
from src.models.manifest_bundle import ManifestBundle
from src.models.policy_rule import PolicyRule
from src.models.violation import Violation
from src.models.user import User
from src.services import bundle_service, exemption_service, policy_service
from src.services.dsl_eval import evaluate_policy_on_docs
from src.services.quota import evaluate_quota, summarize_ns_heat
from src.utils.errors import AppError
from src.utils.logger import get_logger

logger = get_logger("policyeval.run")

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def create_run(
    db: Session,
    *,
    bundle_id: str,
    policy_ids: list[str] | None,
    include_quota: bool,
    user: User,
) -> EvaluationRun:
    bundle = bundle_service.get_bundle(db, bundle_id)
    policies = policy_service.enabled_policies(db, policy_ids)
    if not policies:
        raise AppError(
            codes.VALIDATION_ERROR,
            "没有可执行的启用策略（选中的策略可能已禁用或 DSL 未通过解析）",
            f"bundle={bundle.id}",
        )
    if not include_quota and policy_ids is None:
        include_quota = True  # 全量评估必须包含配额引擎
    run = EvaluationRun(
        id=new_id(),
        bundle_id=str(bundle.id),
        status=RunStatus.RUNNING,
        scope_json=[str(p.id) for p in policies],
        include_quota=include_quota,
        triggered_by=user.email,
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()
    db.commit()  # 先提交，避免 worker 比请求事务更快读不到 run
    dispatched = dispatch_run(str(run.id))
    logger.info(
        "run created id=%s bundle=%s policies=%s quota=%s dispatched=%s",
        run.id,
        bundle.name,
        len(policies),
        include_quota,
        dispatched,
    )
    return run


def dispatch_run(run_id: str) -> bool:
    try:
        celery_app.send_task(TASK_EVALUATE_RUN, args=[run_id])
        return True
    except Exception as exc:  # noqa: BLE001 - broker 抖动时退回同步执行
        logger.warning("celery dispatch failed (%s), falling back to inline execution", exc)
        try:
            execute_run_by_id(run_id)
        except Exception as inline_exc:  # noqa: BLE001
            logger.exception("inline evaluation also failed: %s", inline_exc)
        return False


def execute_run_by_id(run_id: str) -> None:
    """worker 任务入口：独立 session，失败写 failed 状态。"""
    with session_scope() as db:
        run = db.get(EvaluationRun, run_id)
        if run is None:
            logger.warning("evaluate_run: run %s not found", run_id)
            return
        if run.status != RunStatus.RUNNING:
            logger.info("evaluate_run: run %s already %s, skip", run_id, run.status)
            return
        execute_run(db, run)


def execute_run(db: Session, run: EvaluationRun) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        bundle = db.get(ManifestBundle, run.bundle_id)
        if bundle is None:
            raise AppError(codes.NOT_FOUND, "运行关联的清单包不存在", run.bundle_id)
        docs = bundle_service.load_docs(bundle)
        policy_ids = run.scope_json or None
        policies = policy_service.enabled_policies(db, policy_ids)

        # 重试场景：先清掉本 run 已落库的违规
        db.query(Violation).filter(Violation.run_id == str(run.id)).delete()

        rules: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for policy in policies:
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
            result = evaluate_policy_on_docs(policy_dict, docs)
            candidates.extend(result["violations"])
            rules.append(
                {
                    "policy_id": str(policy.id),
                    "code": policy.code,
                    "title": policy.title,
                    "severity": policy.severity,
                    "kind": policy.kind,
                    "evaluated_docs": result["evaluated_docs"],
                    "matched_docs": result["matched_docs"],
                    "violation_count": result["violation_count"],
                    "status": "pass" if result["violation_count"] == 0 else "fail",
                }
            )

        quota_summary: dict[str, Any] | None = None
        if run.include_quota:
            quota_result = evaluate_quota(docs)
            candidates.extend(quota_result["violations"])
            rules.append(
                {
                    "policy_id": None,
                    "code": "QUOTA-ENGINE",
                    "title": "资源规约聚合与配额判定",
                    "severity": "high",
                    "kind": "LimitRange",
                    "evaluated_docs": len(docs),
                    "matched_docs": max(
                        0, len(quota_result["ns_summary"]) - len({v["namespace"] for v in quota_result["violations"]})
                    ),
                    "violation_count": len(quota_result["violations"]),
                    "status": "pass" if not quota_result["violations"] else "fail",
                }
            )
            quota_summary = {
                "ns_summary": quota_result["ns_summary"],
                "heat": summarize_ns_heat(quota_result["ns_summary"]),
                "warnings": quota_result["warnings"][:20],
                "workload_count": quota_result["workload_count"],
                "duplicate_count": quota_result["duplicate_count"],
            }

        # 落库违规
        now = utcnow()
        for item in candidates:
            severity = item.get("severity") or "medium"
            violation = Violation(
                id=new_id(),
                run_id=str(run.id),
                policy_id=item.get("policy_id"),
                rule_code=item.get("rule_code") or "UNKNOWN",
                source=item.get("source") or "dsl",
                resource_kind=item.get("resource_kind") or "",
                resource_name=item.get("resource_name") or "",
                namespace=item.get("namespace") or "",
                severity=severity,
                status="open",
                owner_team=_owner_team(item.get("namespace") or ""),
                evidence_json=item.get("evidence") or {},
                created_at=now,
            )
            db.add(violation)
            db.flush()
            exemption = exemption_service.find_effective_exemption(
                db, violation.policy_id, violation.namespace, violation.resource_name
            )
            if exemption is not None:
                violation.status = "exception"
        db.flush()

        # 过期豁免：approved 且 expires_at < now -> expired（同时把对应违规恢复 open）
        expired = exemption_service.expire_overdue(db)

        rules_passed = sum(1 for rule in rules if rule["violation_count"] == 0)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        run.status = RunStatus.DONE
        run.rules_evaluated = len(rules)
        run.rules_passed = rules_passed
        run.docs_evaluated = len(docs)
        run.violation_count = len(candidates)
        run.finished_at = utcnow()
        run.error_message = ""
        if quota_summary is not None:
            bundle.warnings = (bundle.warnings or [])[:0] + [
                f"quota_engine: workloads={quota_summary['workload_count']} "
                f"duplicates={quota_summary['duplicate_count']} "
                f"ns={len(quota_summary['ns_summary'])}"
            ]
        db.flush()
        logger.info(
            "run done id=%s rules=%s passed=%s docs=%s violations=%s expired_exemptions=%s elapsed=%sms",
            run.id,
            len(rules),
            rules_passed,
            len(docs),
            len(candidates),
            expired,
            elapsed_ms,
        )
        return {
            "run_id": str(run.id),
            "rules": rules,
            "quota_summary": quota_summary,
            "severity_counts": _severity_counts(candidates),
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        logger.exception("run failed id=%s: %s", run.id, exc)
        run.status = RunStatus.FAILED
        run.error_message = str(exc)[:500]
        run.finished_at = utcnow()
        db.flush()
        return {"run_id": str(run.id), "error": str(exc)}


def _owner_team(namespace: str) -> str:
    """命名空间 -> 负责团队（演示映射，真实系统应来自 CMDB）。"""
    mapping = {
        "payments": "支付团队",
        "core": "核心系统团队",
        "risk": "风控团队",
        "mobile": "渠道团队",
        "data": "数据团队",
        "batch": "数据团队",
        "ml": "智能决策团队",
        "obs": "SRE 团队",
        "cicd": "平台团队",
        "mesh": "SRE 团队",
        "security": "安全团队",
        "legacy": "遗留系统组",
    }
    for key, team in mapping.items():
        if key in namespace:
            return team
    return "平台团队"


def _severity_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in candidates:
        severity = item.get("severity") or "medium"
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def run_detail(db: Session, run: EvaluationRun) -> dict[str, Any]:
    """运行详情：规则通过率、严重度分布、namespace 分布、配额摘要。"""
    violations = db.query(Violation).filter(Violation.run_id == str(run.id)).all()
    policy_ids = run.scope_json or []
    policies = (
        db.query(PolicyRule).filter(PolicyRule.id.in_(policy_ids)).all() if policy_ids else []
    )
    policy_map = {str(p.id): p for p in policies}
    counts: dict[str, int] = {}
    for violation in violations:
        key = violation.policy_id or violation.rule_code
        counts[key] = counts.get(key, 0) + 1
    rules: list[dict[str, Any]] = []
    for policy_id in policy_ids:
        policy = policy_map.get(policy_id)
        count = counts.get(policy_id, 0)
        rules.append(
            {
                "policy_id": policy_id,
                "code": policy.code if policy else "?",
                "title": policy.title if policy else "（策略已删除）",
                "severity": policy.severity if policy else "medium",
                "violation_count": count,
                "status": "pass" if count == 0 else "fail",
            }
        )
    quota_count = sum(
        counts.get(code, 0) for code in (QUOTA_RULE_CODE_OVER, QUOTA_RULE_CODE_REQ_GT_LIMIT)
    )
    if run.include_quota:
        rules.append(
            {
                "policy_id": None,
                "code": "QUOTA-ENGINE",
                "title": "资源规约聚合与配额判定",
                "severity": "high",
                "violation_count": quota_count,
                "status": "pass" if quota_count == 0 else "fail",
            }
        )
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    status_counts = {"open": 0, "exception": 0, "fixed": 0}
    namespace_counts: dict[str, int] = {}
    for violation in violations:
        severity_counts[violation.severity] = severity_counts.get(violation.severity, 0) + 1
        status_counts[violation.status] = status_counts.get(violation.status, 0) + 1
        namespace_counts[violation.namespace] = namespace_counts.get(violation.namespace, 0) + 1
    return {
        "rules": rules,
        "severity_counts": severity_counts,
        "status_counts": status_counts,
        "namespace_counts": namespace_counts,
    }


def list_runs(db: Session, *, limit: int = 50, offset: int = 0) -> tuple[list[EvaluationRun], int]:
    query = db.query(EvaluationRun)
    total = query.count()
    items = (
        query.order_by(EvaluationRun.started_at.desc()).offset(offset).limit(limit).all()
    )
    return items, total


def get_run(db: Session, run_id: str) -> EvaluationRun:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise AppError(codes.NOT_FOUND, "评估运行不存在", f"run_id={run_id}")
    return run


def retry_run(db: Session, run: EvaluationRun, user: User) -> EvaluationRun:
    if run.status == RunStatus.DONE:
        raise AppError(codes.RUN_BUSY, "该评估已结束，无需重试", f"run_id={run.id}")
    run.status = RunStatus.RUNNING
    run.error_message = ""
    run.started_at = utcnow()
    run.finished_at = None
    run.triggered_by = user.email
    db.commit()
    dispatch_run(str(run.id))
    return run

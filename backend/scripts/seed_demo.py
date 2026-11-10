"""幂等演示数据入口：`docker compose exec -T backend python -m scripts.seed_demo`。

自然键：
  User.email / ManifestBundle.name / PolicyRule.code / EvaluationRun.run_key /
  Exemption(policy_id, namespace, resource_name) / RemediationAdvice.violation_id

每次执行结束打印**恰好一行**固定格式：
  SEED_SUMMARY users=3 bundles=1 policies=9 runs=3 violations=140 exemptions=6 advices=3
两次执行逐字一致（run 的违规在 seed 运行内用真实引擎算出，不覆盖用户后续新增的运行）。

数据全部为合成数据：不连接真实 K8s 集群 / GitOps 仓库 / 审计系统。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.config.database import init_db, session_scope
from src.constants.roles import ROLE_ADMIN, ROLE_ENGINEER, ROLE_OWNER
from src.models.base import new_id, utcnow
from src.models.evaluation_run import EvaluationRun
from src.models.exemption import Exemption
from src.models.manifest_bundle import ManifestBundle
from src.models.policy_rule import PolicyRule
from src.models.remediation_advice import RemediationAdvice
from src.models.user import User
from src.models.violation import Violation
from src.services import bundle_service, exemption_service, policy_service, remediation_service, run_service
from src.utils.password import hash_password
from scripts import seed_data

STATS = {"users": 0, "bundles": 0, "policies": 0, "runs": 0, "violations": 0, "exemptions": 0, "advices": 0}
SKIPPED = dict(STATS)

DEMO_PASSWORD = "Demo@2026"
DEMO_USERS = [
    ("admin@policyeval.demo", "澜川银行 · 平台管理员", ROLE_ADMIN, None),
    ("engineer@policyeval.demo", "澜川银行 · 策略工程师", ROLE_ENGINEER, None),
    ("owner@policyeval.demo", "支付团队 · 业务 owner", ROLE_OWNER, ["lc-payments", "lc-ml-serving"]),
]

BASE_RUN = datetime(2026, 10, 28, 14, 5, 12)       # 基线全量评估（UTC，本地 22:05）
CHECK_RUN = datetime(2026, 10, 25, 13, 40, 3)      # 单规则抽检复跑（0 违规，UTC）
RUNNING_RUN = datetime(2026, 11, 10, 9, 40, 41)    # 当前正在跑的评估（UTC，本地 17:40）
APPROVED_EXPIRES = datetime(2027, 1, 31, 15, 59, 59)
PENDING_EXPIRES = datetime(2027, 2, 28, 15, 59, 59)
EXPIRED_EXPIRES = datetime(2026, 9, 30, 15, 59, 59)


def _count_once(table: str, created: bool) -> None:
    if created:
        STATS[table] += 1
    else:
        SKIPPED[table] += 1


# ------------------------------------------------------------------ users ----


def seed_users(db) -> dict[str, User]:
    users: dict[str, User] = {}
    for email, display_name, role, scope in DEMO_USERS:
        existing = db.query(User).filter(User.email == email).one_or_none()
        if existing is None:
            user = User(
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name=display_name,
                role=role,
                scope_namespaces=scope,
                is_active=True,
            )
            db.add(user)
            db.flush()
            _count_once("users", True)
        else:
            user = existing
            _count_once("users", False)
        users[role] = user
    return users


# ----------------------------------------------------------------- bundle ----


def seed_bundle(db) -> tuple[ManifestBundle, dict[str, Any]]:
    manifests = seed_data.build_manifests()
    existing = (
        db.query(ManifestBundle).filter(ManifestBundle.name == seed_data.BUNDLE_NAME).one_or_none()
    )
    if existing is not None:
        _count_once("bundles", False)
        return existing, manifests
    bundle = bundle_service.create_seed_bundle(
        db,
        name=seed_data.BUNDLE_NAME,
        yaml_text=manifests["yaml_text"],
        docs=manifests["docs"],
        cluster=seed_data.CLUSTER,
        k8s_version=seed_data.K8S_VERSION,
        file_count=manifests["file_count"],
        imported_by="engineer@policyeval.demo",
    )
    _count_once("bundles", True)
    return bundle, manifests


# --------------------------------------------------------------- policies ----


def seed_policies(db) -> dict[str, PolicyRule]:
    policies: dict[str, PolicyRule] = {}
    for spec in seed_data.POLICIES:
        policy, created = policy_service.seed_policy(db, {**spec, "created_by": "engineer@policyeval.demo"})
        policies[spec["code"]] = policy
        _count_once("policies", created)
    return policies


# ------------------------------------------------------------------- runs ----


def _find_run(db, run_key: str) -> EvaluationRun | None:
    return db.query(EvaluationRun).filter(EvaluationRun.run_key == run_key).one_or_none()


def seed_check_run(db, bundle: ManifestBundle, policies: dict[str, PolicyRule], engineer: User) -> EvaluationRun:
    run_key = "seed-check-20261025"
    existing = _find_run(db, run_key)
    if existing is not None:
        _count_once("runs", False)
        return existing
    run = EvaluationRun(
        id=new_id(),
        run_key=run_key,
        bundle_id=str(bundle.id),
        status="running",
        scope_json=[str(policies["CIS-5.2.1"].id)],
        include_quota=False,
        triggered_by=engineer.email,
        started_at=CHECK_RUN,
    )
    db.add(run)
    db.flush()
    run_service.execute_run(db, run)
    run.started_at = CHECK_RUN
    run.finished_at = CHECK_RUN + timedelta(seconds=4)
    db.flush()
    _count_once("runs", True)
    return run


def seed_baseline_run(db, bundle: ManifestBundle, policies: dict[str, PolicyRule], engineer: User) -> EvaluationRun:
    run_key = "seed-baseline-2026q4"
    existing = _find_run(db, run_key)
    if existing is not None:
        _count_once("runs", False)
        STATS["violations"] += db.query(Violation).filter(Violation.run_id == str(existing.id)).count()
        return existing
    enabled = [p for p in policies.values() if p.enabled and p.ast_json]
    run = EvaluationRun(
        id=new_id(),
        run_key=run_key,
        bundle_id=str(bundle.id),
        status="running",
        scope_json=[str(p.id) for p in enabled],
        include_quota=True,
        triggered_by=engineer.email,
        started_at=BASE_RUN,
    )
    db.add(run)
    db.flush()
    run_service.execute_run(db, run)
    run.started_at = BASE_RUN
    run.finished_at = BASE_RUN + timedelta(seconds=47)
    db.flush()
    STATS["violations"] += db.query(Violation).filter(Violation.run_id == str(run.id)).count()
    _count_once("runs", True)
    return run


def seed_running_run(db, bundle: ManifestBundle, policies: dict[str, PolicyRule], engineer: User) -> EvaluationRun:
    run_key = "seed-running-20261110"
    existing = _find_run(db, run_key)
    if existing is not None:
        _count_once("runs", False)
        return existing
    enabled = [p for p in policies.values() if p.enabled and p.ast_json]
    run = EvaluationRun(
        id=new_id(),
        run_key=run_key,
        bundle_id=str(bundle.id),
        status="running",
        scope_json=[str(p.id) for p in enabled],
        include_quota=True,
        triggered_by=engineer.email,
        started_at=RUNNING_RUN,
    )
    db.add(run)
    db.flush()
    _count_once("runs", True)
    return run


# -------------------------------------------------------------- violations ----


def _pick_violation(
    db, run_id: str, *, policy_code: str, namespace: str | None = None
) -> Violation | None:
    query = (
        db.query(Violation)
        .join(PolicyRule, PolicyRule.id == Violation.policy_id)
        .filter(Violation.run_id == run_id)
        .filter(PolicyRule.code == policy_code)
    )
    if namespace:
        query = query.filter(Violation.namespace == namespace)
    return query.order_by(Violation.namespace.asc(), Violation.resource_name.asc()).first()


def _exemption_exists(db, policy_id: str, namespace: str, resource_name: str) -> bool:
    return (
        db.query(Exemption)
        .filter(Exemption.policy_id == policy_id)
        .filter(Exemption.namespace == namespace)
        .filter(Exemption.resource_name == resource_name)
        .first()
        is not None
    )


def seed_exemptions(db, run: EvaluationRun, policies: dict[str, PolicyRule], users: dict[str, User]) -> None:
    admin = users[ROLE_ADMIN]
    owner = users[ROLE_OWNER]
    engineer = users[ROLE_ENGINEER]

    approved_plan = [
        ("CIS-5.7.6", "lc-core-banking", "遗留结算系统镜像暂不支持非 root（迁移窗口 2027Q1）"),
        ("CIS-5.7.6", "lc-risk-engine", "风控模型容器依赖 root 写入共享缓存卷，已走补偿控制"),
        ("CIS-5.7.6", "lc-data-platform", "数据抽取容器需要 root 读取宿主机审计设备，已加主机侧审计"),
    ]
    for code, namespace, reason in approved_plan:
        violation = _pick_violation(db, str(run.id), policy_code=code, namespace=namespace)
        if violation is None:
            continue
        policy = policies[code]
        if _exemption_exists(db, str(policy.id), namespace, violation.resource_name):
            SKIPPED["exemptions"] += 1
            continue
        exemption = Exemption(
            id=new_id(),
            policy_id=str(policy.id),
            namespace=namespace,
            resource_name=violation.resource_name,
            reason=reason,
            requested_by=owner.email,
            status="pending",
            expires_at=APPROVED_EXPIRES,
            created_at=BASE_RUN + timedelta(days=2),
        )
        db.add(exemption)
        db.flush()
        exemption_service.decide(db, exemption, "approve", "审计前专项评审通过，补偿控制已登记", admin)
        STATS["exemptions"] += 1

    pending_plan = [
        ("CIS-5.2.2", "lc-payments", "支付网关压测中，limits 待压测数据确认后补齐", owner.email),
        ("CIS-5.2.2", "lc-ml-serving", "模型推理容器内存波动大，等待 profiling 结果", engineer.email),
    ]
    for code, namespace, reason, requested_by in pending_plan:
        violation = _pick_violation(db, str(run.id), policy_code=code, namespace=namespace)
        if violation is None:
            continue
        policy = policies[code]
        if _exemption_exists(db, str(policy.id), namespace, violation.resource_name):
            SKIPPED["exemptions"] += 1
            continue
        db.add(
            Exemption(
                id=new_id(),
                policy_id=str(policy.id),
                namespace=namespace,
                resource_name=violation.resource_name,
                reason=reason,
                requested_by=requested_by,
                status="pending",
                expires_at=PENDING_EXPIRES,
                created_at=BASE_RUN + timedelta(days=3),
            )
        )
        db.flush()
        STATS["exemptions"] += 1

    expired_code, expired_ns = "CIS-5.7.9", "lc-legacy"
    violation = _pick_violation(db, str(run.id), policy_code=expired_code, namespace=expired_ns)
    if violation is not None:
        policy = policies[expired_code]
        if _exemption_exists(db, str(policy.id), expired_ns, violation.resource_name):
            SKIPPED["exemptions"] += 1
        else:
            db.add(
                Exemption(
                    id=new_id(),
                    policy_id=str(policy.id),
                    namespace=expired_ns,
                    resource_name=violation.resource_name,
                    reason="历史镜像 tag 冻结窗口（已于 2026-09-30 到期）",
                    requested_by=owner.email,
                    approved_by=admin.email,
                    status="expired",
                    expires_at=EXPIRED_EXPIRES,
                    decided_at=datetime(2026, 6, 30, 2, 0, 0),
                    created_at=datetime(2026, 6, 28, 2, 0, 0),
                )
            )
            db.flush()
            STATS["exemptions"] += 1


def seed_advices(db, run: EvaluationRun, users: dict[str, User]) -> None:
    admin = users[ROLE_ADMIN]
    candidates = [
        _pick_violation(db, str(run.id), policy_code="CIS-5.7.6", namespace="lc-payments"),
        _pick_violation(db, str(run.id), policy_code="CIS-5.2.2", namespace="lc-risk-engine"),
    ]
    quota_violation = (
        db.query(Violation)
        .filter(Violation.run_id == str(run.id))
        .filter(Violation.source == "quota")
        .filter(Violation.rule_code == "QUOTA-OVER")
        .order_by(Violation.namespace.desc())
        .first()
    )
    if quota_violation is not None:
        candidates.append(quota_violation)
    for violation in candidates:
        if violation is None:
            continue
        existing = (
            db.query(RemediationAdvice)
            .filter(RemediationAdvice.violation_id == str(violation.id))
            .one_or_none()
        )
        if existing is not None:
            SKIPPED["advices"] += 1
            continue
        remediation_service.generate(db, violation, admin)
        STATS["advices"] += 1


# ------------------------------------------------------------------ entry ----


def _summary(db) -> dict[str, str]:
    seed_run_count = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.run_key.isnot(None))
        .count()
    )
    violation_count = (
        db.query(Violation)
        .join(EvaluationRun, EvaluationRun.id == Violation.run_id)
        .filter(EvaluationRun.run_key.isnot(None))
        .count()
    )
    return {
        "users": str(db.query(User).count()),
        "bundles": str(db.query(ManifestBundle).count()),
        "policies": str(db.query(PolicyRule).count()),
        "runs": str(seed_run_count),
        "violations": str(violation_count),
        "exemptions": str(db.query(Exemption).count()),
        "advices": str(db.query(RemediationAdvice).count()),
    }


def seed_all() -> dict[str, Any]:
    init_db()
    with session_scope() as db:
        users = seed_users(db)
        bundle, _manifests = seed_bundle(db)
        policies = seed_policies(db)
        engineer = users[ROLE_ENGINEER]
        seed_check_run(db, bundle, policies, engineer)
        run = seed_baseline_run(db, bundle, policies, engineer)
        seed_running_run(db, bundle, policies, engineer)
        seed_exemptions(db, run, policies, users)
        seed_advices(db, run, users)
        summary = _summary(db)

    line = " ".join(f"{key}={summary[key]}" for key in ("users", "bundles", "policies", "runs", "violations", "exemptions", "advices"))
    print(f"SEED_SUMMARY {line}", flush=True)
    return {
        "created": sum(STATS.values()),
        "skipped": sum(SKIPPED.values()),
        "summary": summary,
        "stats": STATS,
        "skipped_detail": SKIPPED,
    }


if __name__ == "__main__":
    result = seed_all()
    print(
        f"[seed] created={result['created']} skipped={result['skipped']}",
        flush=True,
    )

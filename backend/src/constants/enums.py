"""后端共享枚举（与 frontend/src/constants/enums.ts 一一对应）。

出现位置（后端）：models/*、schemas/*、services/dsl_eval.py、services/quota.py、
seed_demo.py、README「枚举出现位置」。
"""
from __future__ import annotations


class PolicySeverity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    ALL: tuple[str, ...] = (LOW, MEDIUM, HIGH, CRITICAL)


class RuleKind:
    POD = "Pod"
    DEPLOYMENT = "Deployment"
    NAMESPACE = "Namespace"
    LIMIT_RANGE = "LimitRange"
    ALL: tuple[str, ...] = (POD, DEPLOYMENT, NAMESPACE, LIMIT_RANGE)


class ViolationStatus:
    OPEN = "open"
    EXCEPTION = "exception"
    FIXED = "fixed"
    ALL: tuple[str, ...] = (OPEN, EXCEPTION, FIXED)


class ViolationSource:
    DSL = "dsl"
    QUOTA = "quota"
    ALL: tuple[str, ...] = (DSL, QUOTA)


class RunStatus:
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    ALL: tuple[str, ...] = (RUNNING, DONE, FAILED)


class ExemptionStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ALL: tuple[str, ...] = (PENDING, APPROVED, REJECTED, EXPIRED)


class EffortLevel:
    S = "S"
    M = "M"
    L = "L"
    ALL: tuple[str, ...] = (S, M, L)


class BundleSource:
    GITOPS = "gitops"
    UPLOAD = "upload"
    ALL: tuple[str, ...] = (GITOPS, UPLOAD)


SEVERITY_ORDER: dict[str, int] = {
    PolicySeverity.CRITICAL: 4,
    PolicySeverity.HIGH: 3,
    PolicySeverity.MEDIUM: 2,
    PolicySeverity.LOW: 1,
}

SEVERITY_LABELS: dict[str, str] = {
    PolicySeverity.CRITICAL: "严重",
    PolicySeverity.HIGH: "高",
    PolicySeverity.MEDIUM: "中",
    PolicySeverity.LOW: "低",
}

VIOLATION_STATUS_LABELS: dict[str, str] = {
    ViolationStatus.OPEN: "待整改",
    ViolationStatus.EXCEPTION: "已豁免",
    ViolationStatus.FIXED: "已修复",
}

RUN_STATUS_LABELS: dict[str, str] = {
    RunStatus.RUNNING: "运行中",
    RunStatus.DONE: "已完成",
    RunStatus.FAILED: "失败",
}

EXEMPTION_STATUS_LABELS: dict[str, str] = {
    ExemptionStatus.PENDING: "待审批",
    ExemptionStatus.APPROVED: "已通过",
    ExemptionStatus.REJECTED: "已驳回",
    ExemptionStatus.EXPIRED: "已过期",
}

RULE_KIND_LABELS: dict[str, str] = {
    RuleKind.POD: "Pod",
    RuleKind.DEPLOYMENT: "Deployment",
    RuleKind.NAMESPACE: "Namespace",
    RuleKind.LIMIT_RANGE: "LimitRange",
}

# quota 算法使用的合成规则码（Violation.policy_id 为空时用于展示）
QUOTA_RULE_CODE_OVER = "QUOTA-OVER"
QUOTA_RULE_CODE_REQ_GT_LIMIT = "QUOTA-REQ_GT_LIMIT"
QUOTA_RULE_TITLES: dict[str, str] = {
    QUOTA_RULE_CODE_OVER: "资源规约超出 ResourceQuota/平台阈值",
    QUOTA_RULE_CODE_REQ_GT_LIMIT: "requests 大于 limits",
}

"""整改建议服务：根据违规 evidence 生成可执行的 patch YAML + 影响面估算。

patch 结构是 Kubernetes 对象的最小片段（容器级改动用 strategic merge 片段形式），
不是对真实集群执行 patch —— 见 README/TESTING「已知差异」。
"""
from __future__ import annotations

from typing import Any

import yaml
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import (
    QUOTA_RULE_CODE_OVER,
    QUOTA_RULE_CODE_REQ_GT_LIMIT,
    PolicySeverity,
)
from src.models.base import new_id, utcnow
from src.models.remediation_advice import RemediationAdvice
from src.models.user import User
from src.models.violation import Violation
from src.utils.errors import AppError

EFFORT_BY_SEVERITY = {
    PolicySeverity.CRITICAL: "L",
    PolicySeverity.HIGH: "M",
    PolicySeverity.MEDIUM: "M",
    PolicySeverity.LOW: "S",
}
ESTIMATED_MINUTES = {
    PolicySeverity.CRITICAL: 90,
    PolicySeverity.HIGH: 45,
    PolicySeverity.MEDIUM: 25,
    PolicySeverity.LOW: 10,
}


def _resource_of(violation: Violation) -> dict[str, Any]:
    evidence = violation.evidence_json or {}
    resource = evidence.get("resource") or {}
    return {
        "kind": resource.get("kind") or violation.resource_kind,
        "name": resource.get("name") or violation.resource_name,
        "namespace": resource.get("namespace") or violation.namespace,
        "replicas": resource.get("replicas"),
        "containers": resource.get("containers") or [],
        "labels": resource.get("labels") or [],
    }


def _container_names(resource: dict[str, Any]) -> list[str]:
    names = [str(item.get("name")) for item in resource.get("containers") or [] if item.get("name")]
    return names or ["<container-name>"]


def _api_version(kind: str) -> str:
    if kind == "Deployment":
        return "apps/v1"
    if kind in ("StatefulSet", "DaemonSet"):
        return "apps/v1"
    return "v1"


def _deployment_patch(resource: dict[str, Any], containers_patch: list[dict[str, Any]], extra_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    kind = resource["kind"] or "Deployment"
    template_spec: dict[str, Any] = {"containers": containers_patch}
    patch: dict[str, Any] = {
        "apiVersion": _api_version(str(kind)),
        "kind": kind,
        "metadata": {"name": resource["name"], "namespace": resource["namespace"]},
        "spec": {"template": {"spec": template_spec}},
    }
    if extra_spec:
        patch["spec"].update(extra_spec)
        if "replicas" in extra_spec:
            patch["spec"]["template"] = {"spec": template_spec}
    return patch


def _build_patch(violation: Violation) -> tuple[str, dict[str, Any]]:
    resource = _resource_of(violation)
    code = violation.rule_code
    containers = _container_names(resource)
    header = [
        f"# policyeval remediation · {code}",
        f"# 违规: {violation.resource_kind}/{violation.namespace}/{violation.resource_name}",
        "# 该片段用于业务团队 GitOps 仓库合并；平台不会直接下发到集群。",
    ]
    impact = {
        "namespace": resource["namespace"],
        "resource_kind": resource["kind"],
        "resource_name": resource["name"],
        "containers": containers,
        "effort": EFFORT_BY_SEVERITY.get(violation.severity, "M"),
        "estimated_minutes": ESTIMATED_MINUTES.get(violation.severity, 30),
        "risk": "低" if violation.severity in (PolicySeverity.LOW, PolicySeverity.MEDIUM) else "中",
        "verify": f"修复后重跑策略 {code}，该资源命中应变为 0",
    }
    code_upper = (code or "").upper()
    if code == QUOTA_RULE_CODE_OVER:
        evidence = violation.evidence_json or {}
        used = (evidence.get("used") or {}).get("display")
        threshold = (evidence.get("threshold") or {}).get("display")
        metric = evidence.get("metric")
        quota = {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {
                "name": f"{resource['namespace']}-quota",
                "namespace": resource["namespace"],
            },
            "spec": {
                "hard": {
                    metric.split(".")[0] + "." + metric.split(".")[1]: threshold,
                }
            },
        }
        guidance = {
            "option_a_raise_quota": quota,
            "option_b_reduce_workload": {
                "namespace": resource["namespace"],
                "current_usage": used,
                "target_usage": threshold,
                "actions": [
                    "降低 Deployment replicas 或单容器 requests",
                    "把批处理负载迁到独立命名空间",
                ],
            },
        }
        impact["evidence_used"] = used
        impact["evidence_threshold"] = threshold
        impact["metric"] = metric
        impact["note"] = "配额类违规需要平台审批上调阈值，或业务团队压缩 requests/limits"
        text = "\n".join(header) + "\n" + yaml.safe_dump(
            guidance, allow_unicode=True, sort_keys=False
        )
        return text, impact
    if code == QUOTA_RULE_CODE_REQ_GT_LIMIT:
        evidence = violation.evidence_json or {}
        container = evidence.get("container") or containers[0]
        req_cpu = (evidence.get("requests.cpu") or {}).get("display")
        lim_cpu = (evidence.get("limits.cpu") or {}).get("display")
        patch = _deployment_patch(
            resource,
            [
                {
                    "name": container,
                    "resources": {
                        "limits": {
                            "cpu": req_cpu or "1",
                            "memory": (evidence.get("requests.memory") or {}).get("display")
                            or "1Gi",
                        }
                    },
                }
            ],
        )
        impact["container"] = container
        impact["before"] = {"requests.cpu": req_cpu, "limits.cpu": lim_cpu}
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    if code == "CIS-5.7.6":
        patch = _deployment_patch(
            resource,
            [{"name": name, "securityContext": {"runAsNonRoot": True, "runAsUser": 1000}} for name in containers],
        )
        impact["action"] = "为每个容器补 securityContext.runAsNonRoot=true"
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    if code == "CIS-5.2.2":
        patch = _deployment_patch(
            resource,
            [
                {
                    "name": name,
                    "resources": {
                        "requests": {"cpu": "250m", "memory": "256Mi"},
                        "limits": {"cpu": "1", "memory": "1Gi"},
                    },
                }
                for name in containers
            ],
        )
        impact["action"] = "为容器补 requests/limits（示例值需业务团队按压测数据调整）"
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    if code.startswith("CIS-5.4"):
        patch = {
            "apiVersion": _api_version(str(resource["kind"])),
            "kind": resource["kind"],
            "metadata": {
                "name": resource["name"],
                "namespace": resource["namespace"],
                "labels": {"owner": "replace-with-team", "app.kubernetes.io/part-of": "lanchuan-bank"},
            },
        }
        impact["action"] = "补齐 metadata.labels.owner 等治理标签"
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    if code == "CIS-5.2.5":
        patch = {
            "apiVersion": _api_version(str(resource["kind"])),
            "kind": resource["kind"],
            "metadata": {"name": resource["name"], "namespace": resource["namespace"]},
            "spec": {"replicas": 2},
        }
        impact["action"] = "把 replicas 提升到 2，满足关键业务多副本要求"
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    if code == "CIS-5.7.9":
        images = [item.get("image") for item in resource.get("containers") or [] if item.get("image")]
        patch = _deployment_patch(
            resource,
            [
                {
                    "name": name,
                    "image": "registry.lanchuan.bank/<repo>:<pinned-tag-or-digest>",
                }
                for name in containers
            ],
        )
        impact["action"] = "把 :latest 镜像替换为固定语义化 tag 或 digest"
        impact["current_images"] = images
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    if code.startswith("CIS-5.2.1") or resource["kind"] == "Namespace":
        patch = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": resource["name"] or resource["namespace"],
                "labels": {"owner": "replace-with-team"},
            },
        }
        impact["action"] = "补齐 Namespace owner 标签"
        return "\n".join(header) + "\n" + yaml.safe_dump(patch, allow_unicode=True, sort_keys=False), impact
    generic = {
        "apiVersion": _api_version(str(resource["kind"])),
        "kind": resource["kind"],
        "metadata": {"name": resource["name"], "namespace": resource["namespace"]},
        "spec": {"template": {"spec": {"containers": [{"name": containers[0]}]}}},
    }
    impact["action"] = "通用占位 patch：请按策略 DSL 期望值人工确认改动"
    return "\n".join(header) + "\n" + yaml.safe_dump(generic, allow_unicode=True, sort_keys=False), impact


def generate(db: Session, violation: Violation, user: User) -> RemediationAdvice:
    patch_yaml, impact = _build_patch(violation)
    advice = (
        db.query(RemediationAdvice)
        .filter(RemediationAdvice.violation_id == str(violation.id))
        .one_or_none()
    )
    if advice is None:
        advice = RemediationAdvice(
            id=new_id(),
            violation_id=str(violation.id),
            patch_yaml=patch_yaml,
            impact=impact,
            effort_level=impact.get("effort", "M"),
            generated_by=user.email,
            created_at=utcnow(),
        )
        db.add(advice)
    else:
        advice.patch_yaml = patch_yaml
        advice.impact = impact
        advice.effort_level = impact.get("effort", "M")
        advice.generated_by = user.email
    db.flush()
    return advice


def get_advice(db: Session, violation_id: str) -> RemediationAdvice | None:
    return (
        db.query(RemediationAdvice)
        .filter(RemediationAdvice.violation_id == violation_id)
        .one_or_none()
    )

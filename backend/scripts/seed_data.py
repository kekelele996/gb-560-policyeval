"""seed 的清单生成器：12 个命名空间 × 8-12 资源 = 120 个文档（全部合成数据）。

设计要点（与 batch-plan gb-560 对齐）：
- 1 个 bundle「lanchuan-prod 2026Q4」：12 ns、63 Deployment、6 StatefulSet、24 Service、
  12 ConfigMap、2 ResourceQuota、1 LimitRange = 120 文档，12 个文件。
- 2 个故意超配额 ns（lc-payments / lc-ml-serving），配额 hard 值由生成器按目标比例
  反算，保证配额引擎给出的超标比例是真实计算出来的，不是写死的违规行。
- Deployment 上的合规标志（非 root / limits 缺失 / owner 标签 / 副本数 / latest tag）
  按确定索引集合分配，使真实求值恰好得到 planned 的违规分布：
  critical 12（非 root）、high 46（limits 缺失 41 + 配额 5）、
  medium 52（owner 标签 30 + 副本数 22）、low 30（latest tag 30）。
- 所有名字/数值固定，重复生成逐字节一致。
"""
from __future__ import annotations

import math
from typing import Any

import yaml

from src.services.quota import aggregate_namespaces

BUNDLE_NAME = "lanchuan-prod 2026Q4"
CLUSTER = "lanchuan-prod-cn-shanghai"
K8S_VERSION = "v1.29.4"

NAMESPACES: list[dict[str, str]] = [
    {"name": "lc-core-banking", "team": "核心系统团队", "short": "core"},
    {"name": "lc-payments", "team": "支付团队", "short": "payments"},
    {"name": "lc-risk-engine", "team": "风控团队", "short": "risk"},
    {"name": "lc-mobile-gateway", "team": "渠道团队", "short": "mobile"},
    {"name": "lc-data-platform", "team": "数据团队", "short": "data"},
    {"name": "lc-batch-jobs", "team": "数据团队", "short": "batch"},
    {"name": "lc-ml-serving", "team": "智能决策团队", "short": "ml"},
    {"name": "lc-observability", "team": "SRE 团队", "short": "obs"},
    {"name": "lc-cicd", "team": "平台团队", "short": "cicd"},
    {"name": "lc-mesh", "team": "SRE 团队", "short": "mesh"},
    {"name": "lc-security", "team": "安全团队", "short": "security"},
    {"name": "lc-legacy", "team": "遗留系统组", "short": "legacy"},
]

QUOTA_NAMESPACE_REQ = "lc-payments"       # requests 维度故意超配额
QUOTA_NAMESPACE_LIM = "lc-ml-serving"     # limits 维度故意超配额
LIMITRANGE_NAMESPACE = "lc-data-platform"  # 无 ResourceQuota，退回 LimitRange.max

EXTRA_DEPLOYMENT_NS = {"lc-core-banking", "lc-data-platform", "lc-cicd"}
SERVICE_SUFFIXES = ["gateway", "ledger", "settlement", "reconcile", "notify", "router"]
DEPLOYMENTS_PER_NS = 5

DEPLOYMENT_COUNT = sum(
    DEPLOYMENTS_PER_NS + (1 if item["name"] in EXTRA_DEPLOYMENT_NS else 0)
    for item in NAMESPACES
)


def _take(predicate, count: int) -> list[int]:
    picked = [index for index in range(DEPLOYMENT_COUNT) if predicate(index)][:count]
    if len(picked) != count:  # pragma: no cover - 生成器自检
        raise RuntimeError(f"flag 分配不足: 需要 {count} 实际 {len(picked)}")
    return picked


NON_ROOT_VIOLATIONS = _take(lambda i: i % 5 in (0, 2), 12)
LIMITS_MISSING = _take(lambda i: i % 3 != 2, 41)
LABEL_MISSING = _take(lambda i: i % 2 == 0, 30)
REPLICAS_LT2 = _take(lambda i: i % 4 != 3, 22)
LATEST_TAG = _take(lambda i: i % 2 == 1, 30)

# 配额测试专用 Deployment：requests.cpu 2 / limits.cpu 0.5 -> requests>limits
REQ_GT_LIMIT_INDEX = 6  # lc-payments 的第一个 Deployment（core 有 6 个，故从 6 起）
LIMITS_MISSING = [i for i in _take(lambda i: i % 3 != 2, 42) if i != REQ_GT_LIMIT_INDEX][:41]


def build_deployments() -> list[dict[str, Any]]:
    """按确定规则生成 63 个 Deployment 描述（含合规标志）。"""
    registry: list[dict[str, Any]] = []
    index = 0
    for ns in NAMESPACES:
        count = DEPLOYMENTS_PER_NS + (1 if ns["name"] in EXTRA_DEPLOYMENT_NS else 0)
        for slot in range(count):
            suffix = SERVICE_SUFFIXES[slot % len(SERVICE_SUFFIXES)]
            name = f"{ns['short']}-{suffix}"
            replicas = 1 if index in REPLICAS_LT2 else (2 if slot % 2 == 0 else 3)
            containers = 2 + (index % 2)
            registry.append(
                {
                    "index": index,
                    "namespace": ns["name"],
                    "team": ns["team"],
                    "short": ns["short"],
                    "name": name,
                    "replicas": replicas,
                    "containers": containers,
                    "non_root_ok": index not in NON_ROOT_VIOLATIONS,
                    "limits_missing": index in LIMITS_MISSING,
                    "label_missing": index in LABEL_MISSING,
                    "latest_tag": index in LATEST_TAG,
                    "req_gt_limit": index == REQ_GT_LIMIT_INDEX,
                }
            )
            index += 1
    return registry


def _image_for(deployment: dict[str, Any]) -> str:
    repo = f"registry.lanchuan.bank/{deployment['short']}/{deployment['name']}"
    if deployment["latest_tag"]:
        return f"{repo}:latest"
    return f"{repo}:v1.{4 + deployment['index'] % 3}.{deployment['index'] % 7}"


def _resources_for(index: int, container_index: int, missing: bool) -> dict[str, Any]:
    req_cpu = 0.25 + (index % 4) * 0.25 + container_index * 0.1
    req_mem_mi = 256 + ((index + container_index) % 3) * 256
    if missing:
        return {
            "requests": {
                "cpu": f"{req_cpu:g}",
                "memory": f"{req_mem_mi}Mi",
            }
        }
    return {
        "requests": {
            "cpu": f"{req_cpu:g}",
            "memory": f"{req_mem_mi}Mi",
        },
        "limits": {
            "cpu": f"{req_cpu * 2:g}",
            "memory": f"{req_mem_mi * 2}Mi",
        },
    }


def build_deployment_doc(deployment: dict[str, Any]) -> dict[str, Any]:
    containers: list[dict[str, Any]] = []
    for container_index in range(deployment["containers"]):
        container_name = "app" if container_index == 0 else f"sidecar-{container_index}"
        container: dict[str, Any] = {
            "name": container_name,
            "image": _image_for(deployment) if container_index == 0 else "registry.lanchuan.bank/platform/envoy:v1.29.1",
        }
        if deployment["non_root_ok"]:
            container["securityContext"] = {
                "runAsNonRoot": True,
                "runAsUser": 1000,
                "allowPrivilegeEscalation": False,
            }
        if deployment["req_gt_limit"] and container_index == 0:
            container["resources"] = {
                "requests": {"cpu": "2", "memory": "1Gi"},
                "limits": {"cpu": "500m", "memory": "2Gi"},
            }
        else:
            container["resources"] = _resources_for(
                deployment["index"], container_index, deployment["limits_missing"]
            )
        containers.append(container)
    labels = {
        "app": deployment["name"],
        "app.kubernetes.io/part-of": "lanchuan-bank",
        "app.kubernetes.io/managed-by": "argocd",
    }
    if not deployment["label_missing"]:
        labels["owner"] = deployment["team"]
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": deployment["name"],
            "namespace": deployment["namespace"],
            "labels": labels,
        },
        "spec": {
            "replicas": deployment["replicas"],
            "selector": {"matchLabels": {"app": deployment["name"]}},
            "template": {
                "metadata": {"labels": {"app": deployment["name"]}},
                "spec": {"containers": containers},
            },
        },
    }


def build_statefulset_doc(ns: dict[str, str]) -> dict[str, Any]:
    name = f"{ns['short']}-cache"
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {
            "name": name,
            "namespace": ns["name"],
            "labels": {"app": name, "owner": ns["team"]},
        },
        "spec": {
            "replicas": 3,
            "serviceName": name,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [
                        {
                            "name": "redis",
                            "image": "registry.lanchuan.bank/platform/redis:7.2",
                            "resources": {
                                "requests": {"cpu": "500m", "memory": "1Gi"},
                                "limits": {"cpu": "2", "memory": "4Gi"},
                            },
                            "securityContext": {"runAsNonRoot": True, "runAsUser": 1000},
                        }
                    ]
                },
            },
        },
    }


def build_service_doc(ns: dict[str, str], slot: int) -> dict[str, Any]:
    name = f"{ns['short']}-{'gateway' if slot == 0 else 'metrics'}"
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": ns["name"], "labels": {"app": name}},
        "spec": {
            "type": "NodePort" if (slot == 1 and ns["name"] in {"lc-mesh", "lc-observability", "lc-cicd"}) else "ClusterIP",
            "selector": {"app": f"{ns['short']}-gateway"},
            "ports": [
                {"name": "http", "port": 80, "targetPort": 8080, "protocol": "TCP"}
            ],
        },
    }


def build_configmap_doc(ns: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": f"{ns['short']}-config", "namespace": ns["name"]},
        "data": {
            "LOG_LEVEL": "info",
            "CLUSTER": CLUSTER,
            "AUDIT_PIPELINE": "elc-lanchuan-audit",
        },
    }


def build_namespace_doc(ns: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": ns["name"],
            "labels": {
                "owner": ns["team"],
                "env": "prod",
                "compliance": "dengbao-2.0",
            },
        },
    }


def _quota_doc(namespace: str, hard: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {"name": f"{namespace.split('lc-')[1]}-quota", "namespace": namespace},
        "spec": {"hard": hard},
    }


def _limitrange_doc(namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "LimitRange",
        "metadata": {"name": f"{namespace.split('lc-')[1]}-limits", "namespace": namespace},
        "spec": {
            "limits": [
                {
                    "type": "Container",
                    "default": {"cpu": "1", "memory": "1Gi"},
                    "defaultRequest": {"cpu": "250m", "memory": "256Mi"},
                    "max": {"cpu": "64", "memory": "128Gi"},
                }
            ]
        },
    }


def _quota_hard_for(
    totals: dict[str, float],
    *,
    over_dimensions: dict[str, float],
    safe_factor: float = 1.8,
) -> dict[str, str]:
    """按目标超标比例反算 hard 值；非超限维度给足余量，避免误报。"""
    hard: dict[str, str] = {}
    cpu_dims = {"requests.cpu", "limits.cpu"}
    for dimension, used in totals.items():
        ratio = over_dimensions.get(dimension)
        if ratio:
            target = used / ratio
        else:
            target = used * safe_factor
        if dimension in cpu_dims:
            hard[dimension] = f"{max(0.5, round(target, 3)):g}"
        else:
            hard[dimension] = f"{max(1, int(math.ceil(target)))}"
    return hard


def build_manifests() -> dict[str, Any]:
    """生成 120 个文档 + 12 个文件的 YAML 文本 + 部署注册表。"""
    deployments = build_deployments()
    by_ns: dict[str, list[dict[str, Any]]] = {ns["name"]: [] for ns in NAMESPACES}
    registry: list[dict[str, Any]] = []

    for deployment in deployments:
        doc = build_deployment_doc(deployment)
        by_ns[deployment["namespace"]].append(doc)
        registry.append(deployment)

    # 先算出无配额文档时的聚合值，用于反算 2 个故意超配额 ns 的 hard 值
    base_docs: list[dict[str, Any]] = []
    for index, ns in enumerate(NAMESPACES):
        base_docs.append(build_namespace_doc(ns))
        base_docs.extend(by_ns[ns["name"]])
        if index % 2 == 0:
            base_docs.append(build_statefulset_doc(ns))
        base_docs.append(build_service_doc(ns, 0))
        base_docs.append(build_service_doc(ns, 1))
        base_docs.append(build_configmap_doc(ns))
    aggregation = aggregate_namespaces(base_docs)
    totals = aggregation["namespaces"]

    hard_req = _quota_hard_for(
        totals[QUOTA_NAMESPACE_REQ]["resources"],
        over_dimensions={"requests.cpu": 1.34, "requests.memory": 1.28},
    )
    hard_lim = _quota_hard_for(
        totals[QUOTA_NAMESPACE_LIM]["resources"],
        over_dimensions={"limits.cpu": 1.41, "limits.memory": 1.33},
    )

    docs: list[dict[str, Any]] = []
    files: list[str] = []
    for index, ns in enumerate(NAMESPACES):
        file_docs: list[dict[str, Any]] = [build_namespace_doc(ns)]
        file_docs.extend(by_ns[ns["name"]])
        if index % 2 == 0:
            file_docs.append(build_statefulset_doc(ns))
        file_docs.append(build_service_doc(ns, 0))
        file_docs.append(build_service_doc(ns, 1))
        file_docs.append(build_configmap_doc(ns))
        if ns["name"] == QUOTA_NAMESPACE_REQ:
            file_docs.append(_quota_doc(ns["name"], hard_req))
        if ns["name"] == QUOTA_NAMESPACE_LIM:
            file_docs.append(_quota_doc(ns["name"], hard_lim))
        if ns["name"] == LIMITRANGE_NAMESPACE:
            file_docs.append(_limitrange_doc(ns["name"]))
        docs.extend(file_docs)
        files.append(f"clusters/lanchuan-prod/{ns['name']}.yaml")

    yaml_text = (
        f"# {BUNDLE_NAME} · GitOps 导出（合成数据，未连接真实集群）\n"
        f"# cluster={CLUSTER} k8s={K8S_VERSION} files={len(files)}\n"
        + yaml.safe_dump_all(docs, allow_unicode=True, sort_keys=False)
    )
    return {
        "docs": docs,
        "yaml_text": yaml_text,
        "file_count": len(files),
        "files": files,
        "deployments": registry,
        "quota_hard": {
            QUOTA_NAMESPACE_REQ: hard_req,
            QUOTA_NAMESPACE_LIM: hard_lim,
        },
    }


POLICIES: list[dict[str, Any]] = [
    {
        "code": "CIS-5.7.6",
        "title": "容器必须以非 root 用户运行",
        "severity": "critical",
        "kind": "Deployment",
        "dsl_text": "all(spec.template.spec.containers[].securityContext.runAsNonRoot == true)",
        "description": "等保 2.0 8.1.4.1 / CIS 5.7.6：Pod 容器禁止以 root 运行。",
        "enabled": True,
    },
    {
        "code": "CIS-5.2.2",
        "title": "容器必须设置 CPU/内存 limits",
        "severity": "high",
        "kind": "Deployment",
        "dsl_text": (
            "all(hasKey(spec.template.spec.containers[].resources.limits.cpu), "
            "hasKey(spec.template.spec.containers[].resources.limits.memory))"
        ),
        "description": "CIS 5.2.2：未设置 limits 会挤占节点资源。",
        "enabled": True,
    },
    {
        "code": "CIS-5.4.1",
        "title": "Deployment 必须声明 owner 标签",
        "severity": "medium",
        "kind": "Deployment",
        "dsl_text": "all(hasKey(metadata.labels.owner))",
        "description": "整改必须能找到负责团队，owner 标签是豁免与派单的依据。",
        "enabled": True,
    },
    {
        "code": "CIS-5.2.5",
        "title": "关键业务 Deployment 至少 2 副本",
        "severity": "medium",
        "kind": "Deployment",
        "dsl_text": "all(spec.replicas >= 2)",
        "description": "单副本 Deployment 在节点维护时会中断业务。",
        "enabled": True,
    },
    {
        "code": "CIS-5.7.9",
        "title": "镜像 tag 不得使用 latest",
        "severity": "low",
        "kind": "Deployment",
        "dsl_text": "all(not(matches(spec.template.spec.containers[].image, \".*:latest$\")))",
        "description": "latest 无法回滚与审计，要求固定 tag 或 digest。",
        "enabled": True,
    },
    {
        "code": "CIS-5.2.1",
        "title": "Namespace 必须声明 owner 标签且符合命名规范",
        "severity": "low",
        "kind": "Namespace",
        "dsl_text": "all(hasKey(metadata.labels.owner), startsWith(metadata.name, \"lc-\"))",
        "description": "命名空间治理基线，当前全部通过（用于展示通过态）。",
        "enabled": True,
    },
    {
        "code": "CIS-5.3.2",
        "title": "禁止使用 hostNetwork",
        "severity": "high",
        "kind": "Deployment",
        "dsl_text": "all(not(spec.template.spec.hostNetwork == true))",
        "description": "关闭 hostNetwork 避免端口冲突与网络隔离失效；当前全部通过。",
        "enabled": True,
    },
    {
        "code": "CIS-5.7.4",
        "title": "禁止 privileged 特权容器（DSL 待修复）",
        "severity": "high",
        "kind": "Deployment",
        "dsl_text": "all(spec.template.spec.containers[].securityContext.privileged == false",
        "description": "示例：解析失败样本，编辑器会显示缺失右括号的行列位置。",
        "enabled": False,
        "broken": True,
    },
    {
        "code": "CIS-5.5.1",
        "title": "CPU limit 不得超过 4 核（DSL 待修复）",
        "severity": "medium",
        "kind": "Deployment",
        "dsl_text": "all(equals(spec.template.spec.containers[].resources.limits.cpu, 4))",
        "description": "示例：使用了不存在的函数 equals，解析器报未知函数与期望 token。",
        "enabled": False,
        "broken": True,
    },
]

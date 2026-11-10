"""核心算法 2：K8s quantity 解析 + 资源规约聚合 + 配额判定。

口径
----
1. quantity 解析：`500m -> 0.5`、`2 -> 2`、`1Gi -> 1073741824`、`512Mi -> 524288000?`
   不，512Mi = 512 * 1024^2 = 536870912（二进制后缀），`1e3 -> 1000`。
   非法 quantity -> 0 并记 warning（warning 会进入 evidence 与 ns_summary）。
2. 聚合：按 namespace 汇总 Deployment/StatefulSet/DaemonSet/Pod/Job 的
   requests.cpu / requests.memory / limits.cpu / limits.memory；
   Deployment/StatefulSet 按 `spec.replicas` 加权（缺省 1 并记 warning）。
3. 判定：与命名空间 ResourceQuota 的 `hard` 比较；无 ResourceQuota 时退回
   LimitRange 的 `max`；两者都缺时用平台默认阈值（settings 可配）。
   超配额 / requests>limits 产出违规候选，severity 按超限比例分档：
   ratio >= 1.5 -> critical，>= 1.2 -> high，> 1.0 -> medium。
4. 同一 (kind, namespace, name) 重复定义取最后一次并记 warning。

本模块是纯函数（输入 docs 列表，输出结构化结果），不访问数据库。
"""
from __future__ import annotations

import copy
from typing import Any

from src.config.settings import settings
from src.constants.enums import (
    PolicySeverity,
    QUOTA_RULE_CODE_OVER,
    QUOTA_RULE_CODE_REQ_GT_LIMIT,
)

# K8s quantity 后缀：十进制 SI 与二进制 IEC
_DECIMAL_UNITS = {
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "P": 1e15,
    "E": 1e18,
}
_BINARY_UNITS = {
    "Ki": 1024.0,
    "Mi": 1024.0**2,
    "Gi": 1024.0**3,
    "Ti": 1024.0**4,
    "Pi": 1024.0**5,
    "Ei": 1024.0**6,
}
_CPU_DIMS = ("requests.cpu", "limits.cpu")
_MEM_DIMS = ("requests.memory", "limits.memory")
ALL_DIMS = ("requests.cpu", "requests.memory", "limits.cpu", "limits.memory")

WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet", "Pod", "Job", "ReplicaSet")


def apply_quantity_unit(number: float, unit: str) -> float:
    """把数字与 K8s 后缀合成基础单位数值（CPU=核，内存=字节）。"""
    if unit in _BINARY_UNITS:
        return number * _BINARY_UNITS[unit]
    if unit in _DECIMAL_UNITS:
        return number * _DECIMAL_UNITS[unit]
    raise ValueError(f"未知 quantity 后缀: {unit}")


def parse_quantity(raw: Any) -> dict[str, Any]:
    """解析单个 K8s quantity。返回 {value, raw, warning}。非法值 -> 0 + warning。"""
    if raw is None or raw == "":
        return {"value": 0.0, "raw": None, "warning": "empty_quantity"}
    if isinstance(raw, bool):
        return {"value": 0.0, "raw": raw, "warning": "invalid_quantity:bool"}
    if isinstance(raw, (int, float)):
        return {"value": float(raw), "raw": raw, "warning": None}
    text = str(raw).strip()
    import re

    match = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(Ki|Mi|Gi|Ti|Pi|Ei|n|u|m|k|M|G|T|P|E)?",
        text,
    )
    if not match:
        return {"value": 0.0, "raw": raw, "warning": f"invalid_quantity:{text}"}
    number = float(match.group(1))
    unit = match.group(2) or ""
    if number < 0:
        return {"value": 0.0, "raw": raw, "warning": f"negative_quantity:{text}"}
    try:
        return {"value": apply_quantity_unit(number, unit), "raw": raw, "warning": None}
    except ValueError:
        return {"value": 0.0, "raw": raw, "warning": f"unknown_quantity_unit:{text}"}


def format_cpu(value: float) -> dict[str, Any]:
    """CPU 双单位：核 + milli 核。"""
    milli = value * 1000.0
    display = f"{milli:.0f}m" if abs(milli) < 10000 else f"{value:g}"
    return {"value": round(value, 4), "milli": round(milli, 1), "display": display}


def format_memory(value: float) -> dict[str, Any]:
    """内存双单位：字节 + GiB 显示。"""
    gib = value / (1024.0**3)
    return {
        "value": int(round(value)),
        "gib": round(gib, 3),
        "display": f"{gib:.2f}Gi",
    }


def format_dimension(dimension: str, value: float) -> dict[str, Any]:
    if dimension in _CPU_DIMS:
        return format_cpu(value)
    return format_memory(value)


# --------------------------------------------------------------------- 聚合 ----


def _namespace_of(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata") or {}
    namespace = metadata.get("namespace")
    if namespace:
        return str(namespace)
    if doc.get("kind") == "Namespace":
        return str(metadata.get("name") or "")
    return "default"


def _pod_spec(doc: dict[str, Any]) -> dict[str, Any]:
    spec = doc.get("spec") or {}
    kind = doc.get("kind")
    if kind == "Pod":
        return spec
    template = spec.get("template") or {}
    return template.get("spec") or {}


def _containers(doc: dict[str, Any]) -> list[dict[str, Any]]:
    containers = _pod_spec(doc).get("containers") or []
    return [item for item in containers if isinstance(item, dict)]


def _replicas(doc: dict[str, Any], warnings: list[str], ns: str, name: str) -> int:
    kind = doc.get("kind")
    if kind not in ("Deployment", "StatefulSet", "ReplicaSet"):
        return 1
    spec = doc.get("spec") or {}
    if "replicas" not in spec:
        warnings.append(f"{kind}/{ns}/{name}: 缺 spec.replicas，按 1 计算")
        return 1
    raw = spec.get("replicas")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        warnings.append(f"{kind}/{ns}/{name}: spec.replicas={raw!r} 非法，按 1 计算")
        return 1
    return raw


def aggregate_namespaces(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """按 namespace 聚合 requests/limits，返回聚合表 + warnings。"""
    warnings: list[str] = []
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicate_count = 0
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        if kind not in WORKLOAD_KINDS:
            continue
        metadata = doc.get("metadata") or {}
        namespace = _namespace_of(doc)
        name = str(metadata.get("name") or "<unnamed>")
        key = (str(kind), namespace, name)
        if key in seen:
            duplicate_count += 1
            warnings.append(f"{kind}/{namespace}/{name}: 同一资源重复定义，取最后一次")
        seen[key] = doc

    namespaces: dict[str, dict[str, Any]] = {}
    for (kind, namespace, name), doc in seen.items():
        bucket = namespaces.setdefault(
            namespace,
            {
                "namespace": namespace,
                "resources": {dim: 0.0 for dim in ALL_DIMS},
                "workload_count": 0,
                "pod_count": 0,
                "limits_missing": [],
                "requests_gt_limits": [],
                "warnings": [],
                "quota_docs": [],
                "limit_range_docs": [],
            },
        )
        replicas = _replicas(doc, warnings, namespace, name)
        bucket["workload_count"] += 1
        bucket["pod_count"] += replicas
        limits_missing = False
        for container in _containers(doc):
            resources = container.get("resources") or {}
            requests = resources.get("requests") or {}
            limits = resources.get("limits") or {}
            parsed: dict[str, dict[str, Any]] = {}
            for dimension, source in (
                ("requests.cpu", requests.get("cpu")),
                ("requests.memory", requests.get("memory")),
                ("limits.cpu", limits.get("cpu")),
                ("limits.memory", limits.get("memory")),
            ):
                parsed[dimension] = parse_quantity(source)
                if parsed[dimension]["warning"]:
                    warnings.append(
                        f"{kind}/{namespace}/{name}: {dimension} 非法值 "
                        f"{source!r}（{parsed[dimension]['warning']}），按 0 计算"
                    )
                bucket["resources"][dimension] += parsed[dimension]["value"] * replicas
            container_name = str(container.get("name") or "<container>")
            if limits.get("cpu") in (None, "") or limits.get("memory") in (None, ""):
                limits_missing = True
            req_cpu = parsed["requests.cpu"]["value"]
            lim_cpu = parsed["limits.cpu"]["value"]
            req_mem = parsed["requests.memory"]["value"]
            lim_mem = parsed["limits.memory"]["value"]
            if (req_cpu > lim_cpu > 0) or (req_mem > lim_mem > 0):
                bucket["requests_gt_limits"].append(
                    {
                        "kind": kind,
                        "name": name,
                        "container": container_name,
                        "replicas": replicas,
                        "requests.cpu": format_cpu(req_cpu),
                        "limits.cpu": format_cpu(lim_cpu),
                        "requests.memory": format_memory(req_mem),
                        "limits.memory": format_memory(lim_mem),
                    }
                )
        if limits_missing:
            bucket["limits_missing"].append(
                {"kind": kind, "name": name, "replicas": replicas}
            )
    return {
        "namespaces": namespaces,
        "warnings": warnings,
        "duplicate_count": duplicate_count,
        "workload_count": sum(b["workload_count"] for b in namespaces.values()),
    }


# ----------------------------------------------------------------- 配额判定 ----

def _collect_quota_docs(
    docs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    quotas: dict[str, dict[str, Any]] = {}
    limit_ranges: dict[str, dict[str, Any]] = {}
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        namespace = _namespace_of(doc)
        if kind == "ResourceQuota":
            quotas[namespace] = doc
        elif kind == "LimitRange":
            limit_ranges[namespace] = doc
    return {"quotas": quotas, "limit_ranges": limit_ranges}


def _quota_thresholds(
    ns: str,
    quotas: dict[str, dict[str, Any]],
    limit_ranges: dict[str, dict[str, Any]],
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    """每个维度得到 (threshold_value, source)；优先级 ResourceQuota > LimitRange.max > 平台默认。"""
    platform = {
        "requests.cpu": ("requests.cpu", float(settings.PLATFORM_QUOTA_CPU_REQ)),
        "requests.memory": (
            "requests.memory",
            float(settings.PLATFORM_QUOTA_MEM_REQ_GIB) * 1024.0**3,
        ),
        "limits.cpu": ("limits.cpu", float(settings.PLATFORM_QUOTA_CPU_LIM)),
        "limits.memory": (
            "limits.memory",
            float(settings.PLATFORM_QUOTA_MEM_LIM_GIB) * 1024.0**3,
        ),
    }
    thresholds: dict[str, dict[str, Any]] = {}
    quota_doc = quotas.get(ns)
    hard = {}
    if quota_doc:
        hard = ((quota_doc.get("spec") or {}).get("hard")) or {}
    limit_range = limit_ranges.get(ns)
    range_max: dict[str, Any] = {}
    if limit_range:
        for item in ((limit_range.get("spec") or {}).get("limits")) or []:
            if isinstance(item, dict) and item.get("type") == "Container":
                range_max = item.get("max") or {}
                break
    for dimension, (hard_key, default_value) in platform.items():
        if isinstance(hard, dict) and hard.get(hard_key) is not None:
            parsed = parse_quantity(hard.get(hard_key))
            if parsed["warning"]:
                warnings.append(
                    f"ResourceQuota/{ns}: {hard_key} 非法值 {hard.get(hard_key)!r}，退回平台默认"
                )
            else:
                thresholds[dimension] = {
                    "value": parsed["value"],
                    "source": "ResourceQuota",
                    "raw": hard.get(hard_key),
                }
                continue
        range_key = dimension.split(".")[0]
        if isinstance(range_max, dict) and range_max.get(range_key) is not None:
            parsed = parse_quantity(range_max.get(range_key))
            if parsed["warning"]:
                warnings.append(
                    f"LimitRange/{ns}: {range_key} 非法值 {range_max.get(range_key)!r}，退回平台默认"
                )
            else:
                thresholds[dimension] = {
                    "value": parsed["value"],
                    "source": "LimitRange",
                    "raw": range_max.get(range_key),
                }
                continue
        thresholds[dimension] = {
            "value": default_value,
            "source": "platform-default",
            "raw": format_dimension(dimension, default_value)["display"],
        }
    return thresholds


def _severity_for_ratio(ratio: float) -> str:
    if ratio >= 1.5:
        return PolicySeverity.CRITICAL
    if ratio >= 1.2:
        return PolicySeverity.HIGH
    return PolicySeverity.MEDIUM


def _dim_display(dimension: str, value: float) -> dict[str, Any]:
    return format_dimension(dimension, value)


def evaluate_quota(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """配额判定入口：返回 ns_summary 与违规候选（供 run_service 落库）。"""
    aggregation = aggregate_namespaces(docs)
    namespaces = aggregation["namespaces"]
    warnings: list[str] = list(aggregation["warnings"])
    quota_docs = _collect_quota_docs(docs)
    all_ns = sorted(set(list(namespaces.keys()) + list(quota_docs["quotas"].keys())))
    ns_summary: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    for ns in all_ns:
        bucket = namespaces.get(
            ns,
            {
                "namespace": ns,
                "resources": {dim: 0.0 for dim in ALL_DIMS},
                "workload_count": 0,
                "pod_count": 0,
                "limits_missing": [],
                "requests_gt_limits": [],
                "warnings": [],
            },
        )
        thresholds = _quota_thresholds(ns, quota_docs["quotas"], quota_docs["limit_ranges"], warnings)
        dims: dict[str, dict[str, Any]] = {}
        ns_status = "ok"
        for dimension in ALL_DIMS:
            used = bucket["resources"][dimension]
            threshold = thresholds[dimension]["value"]
            ratio = (used / threshold) if threshold > 0 else (float("inf") if used > 0 else 0.0)
            over = used > threshold
            percent = round((ratio - 1.0) * 100.0, 2) if over else round(ratio * 100.0, 2)
            dims[dimension] = {
                "used": _dim_display(dimension, used),
                "threshold": _dim_display(dimension, threshold),
                "threshold_source": thresholds[dimension]["source"],
                "threshold_raw": thresholds[dimension]["raw"],
                "ratio": None if ratio == float("inf") else round(ratio, 4),
                "over_pct": percent,
                "status": "over" if over else ("warn" if ratio >= 0.8 else "ok"),
                "over": over,
            }
            if over:
                ns_status = "over"
            elif ratio >= 0.8 and ns_status != "over":
                ns_status = "warn"
        ns_summary.append(
            {
                "namespace": ns,
                "status": ns_status,
                "workload_count": bucket["workload_count"],
                "pod_count": bucket["pod_count"],
                "limits_missing_count": len(bucket["limits_missing"]),
                "limits_missing": bucket["limits_missing"][:8],
                "requests_gt_limits_count": len(bucket["requests_gt_limits"]),
                "requests_gt_limits": bucket["requests_gt_limits"][:8],
                "dimensions": dims,
                "has_resource_quota": ns in quota_docs["quotas"],
                "has_limit_range": ns in quota_docs["limit_ranges"],
            }
        )
        for dimension in ALL_DIMS:
            item = dims[dimension]
            if not item["over"]:
                continue
            ratio = item["ratio"] or 0.0
            violations.append(
                {
                    "policy_id": None,
                    "rule_code": QUOTA_RULE_CODE_OVER,
                    "source": "quota",
                    "resource_kind": "Namespace",
                    "resource_name": ns,
                    "namespace": ns,
                    "severity": _severity_for_ratio(ratio),
                    "evidence": {
                        "algorithm": "quota-aggregation",
                        "metric": dimension,
                        "namespace": ns,
                        "used": dims[dimension]["used"],
                        "threshold": dims[dimension]["threshold"],
                        "threshold_source": dims[dimension]["threshold_source"],
                        "ratio": item["ratio"],
                        "over_pct": item["over_pct"],
                        "formula": "used = Σ(container requests/limits × replicas)",
                        "workload_count": bucket["workload_count"],
                        "pod_count": bucket["pod_count"],
                        "sample_workloads": [
                            {"kind": w["kind"], "name": w["name"], "replicas": w["replicas"]}
                            for w in bucket["limits_missing"][:3]
                        ],
                        "warnings": [w for w in warnings if ns in w][:6],
                    },
                }
            )
        for item in bucket["requests_gt_limits"]:
            violations.append(
                {
                    "policy_id": None,
                    "rule_code": QUOTA_RULE_CODE_REQ_GT_LIMIT,
                    "source": "quota",
                    "resource_kind": str(item["kind"]),
                    "resource_name": str(item["name"]),
                    "namespace": ns,
                    "severity": PolicySeverity.HIGH,
                    "evidence": {
                        "algorithm": "quota-aggregation",
                        "metric": "requests>limits",
                        "namespace": ns,
                        "container": item["container"],
                        "replicas": item["replicas"],
                        "requests.cpu": item["requests.cpu"],
                        "limits.cpu": item["limits.cpu"],
                        "requests.memory": item["requests.memory"],
                        "limits.memory": item["limits.memory"],
                        "rule": "requests.cpu > limits.cpu 或 requests.memory > limits.memory",
                    },
                }
            )

    return {
        "ns_summary": ns_summary,
        "violations": violations,
        "warnings": warnings,
        "duplicate_count": aggregation["duplicate_count"],
        "workload_count": aggregation["workload_count"],
    }


def summarize_ns_heat(ns_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """给前端 NsHeatBar 的轻量序列：ns + 超标维度数 + 最大超标百分比。"""
    heat: list[dict[str, Any]] = []
    for item in ns_summary:
        over_dims = [d for d, value in item["dimensions"].items() if value["over"]]
        max_pct = max(
            (value["over_pct"] for value in item["dimensions"].values() if value["over"]),
            default=0.0,
        )
        heat.append(
            {
                "namespace": item["namespace"],
                "status": item["status"],
                "over_dimension_count": len(over_dims),
                "max_over_pct": max_pct,
                "workload_count": item["workload_count"],
                "limits_missing_count": item["limits_missing_count"],
            }
        )
    return heat


def deep_copy_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return copy.deepcopy(docs)

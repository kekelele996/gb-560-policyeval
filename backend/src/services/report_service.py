"""合规报告服务：把一次评估运行的违规/豁免汇总成可导出的报告。

合规分口径（README 同步说明）：
    compliance_score = round(100 * rules_passed / rules_evaluated)
即「规则通过率」，不按违规条数加权；已豁免违规在状态里单列，不冲抵规则命中，
避免用大量豁免把分数"洗白"。导出为 Markdown 文本，前端下载为 .md。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import (
    EXEMPTION_STATUS_LABELS,
    QUOTA_RULE_CODE_OVER,
    QUOTA_RULE_CODE_REQ_GT_LIMIT,
    SEVERITY_LABELS,
    VIOLATION_STATUS_LABELS,
    PolicySeverity,
    RunStatus,
)
from src.models.exemption import Exemption
from src.models.manifest_bundle import ManifestBundle
from src.models.policy_rule import PolicyRule
from src.models.user import User
from src.models.violation import Violation
from src.models.evaluation_run import EvaluationRun
from src.utils.errors import AppError


def _latest_done_run(db: Session) -> EvaluationRun | None:
    return (
        db.query(EvaluationRun)
        .filter(EvaluationRun.status == RunStatus.DONE)
        .order_by(EvaluationRun.started_at.desc())
        .first()
    )


def build(db: Session, *, user: User, run_id: str | None = None) -> dict[str, Any]:
    run = db.get(EvaluationRun, run_id) if run_id else _latest_done_run(db)
    if run is None:
        raise AppError(codes.NOT_FOUND, "还没有已完成的评估运行，无法生成报告", "run_id is empty")
    query = db.query(Violation).filter(Violation.run_id == str(run.id))
    if user.role == "owner" and user.scope_namespaces:
        query = query.filter(Violation.namespace.in_(user.scope_namespaces))
    violations = query.all()
    policy_ids = {v.policy_id for v in violations if v.policy_id}
    policies = (
        {str(p.id): p for p in db.query(PolicyRule).filter(PolicyRule.id.in_(policy_ids)).all()}
        if policy_ids
        else {}
    )
    severity_counts = {key: 0 for key in PolicySeverity.ALL}
    status_counts = {"open": 0, "exception": 0, "fixed": 0}
    policy_rows: dict[str, dict[str, Any]] = {}
    ns_rows: dict[str, dict[str, Any]] = {}
    quota_hotspots: list[dict[str, Any]] = []
    critical_samples: list[dict[str, Any]] = []
    for violation in violations:
        severity_counts[violation.severity] = severity_counts.get(violation.severity, 0) + 1
        status_counts[violation.status] = status_counts.get(violation.status, 0) + 1
        policy = policies.get(str(violation.policy_id)) if violation.policy_id else None
        code = policy.code if policy else violation.rule_code
        row = policy_rows.setdefault(
            code,
            {
                "code": code,
                "title": policy.title if policy else "资源规约聚合与配额判定",
                "severity": policy.severity if policy else violation.severity,
                "total": 0,
                "open": 0,
                "exception": 0,
                "fixed": 0,
            },
        )
        row["total"] += 1
        row[violation.status] = row.get(violation.status, 0) + 1
        ns = ns_rows.setdefault(
            violation.namespace,
            {"namespace": violation.namespace, "total": 0, "open": 0, "exception": 0, "fixed": 0},
        )
        ns["total"] += 1
        ns[violation.status] = ns.get(violation.status, 0) + 1
        if violation.source == "quota" and violation.rule_code == QUOTA_RULE_CODE_OVER:
            evidence = violation.evidence_json or {}
            quota_hotspots.append(
                {
                    "namespace": violation.namespace,
                    "metric": evidence.get("metric"),
                    "used": (evidence.get("used") or {}).get("display"),
                    "threshold": (evidence.get("threshold") or {}).get("display"),
                    "source": evidence.get("threshold_source"),
                    "over_pct": evidence.get("over_pct"),
                }
            )
        if violation.severity == PolicySeverity.CRITICAL and status_counts.get("open", 0) and violation.status == "open":
            evidence = violation.evidence_json or {}
            failed = [leaf for leaf in evidence.get("leaf_results") or [] if not leaf.get("passed")]
            critical_samples.append(
                {
                    "code": code,
                    "namespace": violation.namespace,
                    "resource": violation.resource_name,
                    "evidence_path": failed[0]["path"] if failed else "",
                    "actual": failed[0].get("actual") if failed else None,
                    "expected": failed[0].get("expected") if failed else None,
                }
            )
    exemption_query = db.query(Exemption)
    if user.role == "owner" and user.scope_namespaces:
        exemption_query = exemption_query.filter(Exemption.namespace.in_(user.scope_namespaces))
    exemptions = exemption_query.all()
    exemption_counts = {status: 0 for status in ("pending", "approved", "rejected", "expired")}
    for item in exemptions:
        exemption_counts[item.status] = exemption_counts.get(item.status, 0) + 1
    bundle = db.get(ManifestBundle, run.bundle_id)
    rules_evaluated = max(1, run.rules_evaluated or 0)
    compliance_score = round(100 * (run.rules_passed or 0) / rules_evaluated)
    return {
        "run": {
            "id": str(run.id),
            "bundle_id": str(run.bundle_id),
            "bundle_name": bundle.name if bundle else "",
            "status": run.status,
            "rules_evaluated": run.rules_evaluated,
            "rules_passed": run.rules_passed,
            "docs_evaluated": run.docs_evaluated,
            "violation_count": run.violation_count,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_by": user.email,
        "compliance_score": compliance_score,
        "score_formula": "round(100 * rules_passed / rules_evaluated)",
        "totals": {
            "violations": len(violations),
            "open": status_counts["open"],
            "exception": status_counts["exception"],
            "fixed": status_counts["fixed"],
        },
        "severity": {
            key: {"count": value, "label": SEVERITY_LABELS.get(key, key)}
            for key, value in severity_counts.items()
        },
        "status": {
            key: {"count": value, "label": VIOLATION_STATUS_LABELS.get(key, key)}
            for key, value in status_counts.items()
        },
        "policies": sorted(policy_rows.values(), key=lambda item: item["total"], reverse=True),
        "namespaces": sorted(ns_rows.values(), key=lambda item: item["total"], reverse=True),
        "exemptions": {
            "total": len(exemptions),
            "by_status": {
                key: {"count": value, "label": EXEMPTION_STATUS_LABELS.get(key, key)}
                for key, value in exemption_counts.items()
            },
        },
        "quota_hotspots": quota_hotspots,
        "critical_samples": critical_samples[:6],
    }


def export_markdown(report: dict[str, Any]) -> str:
    run = report["run"]
    lines: list[str] = []
    lines.append("# 澜川银行云原生平台 · K8s 策略合规评估报告")
    lines.append("")
    lines.append(f"- 清单包：{run['bundle_name']}（{run['docs_evaluated']} 个文档）")
    lines.append(f"- 评估运行：`{run['id']}`（状态 {run['status']}）")
    lines.append(f"- 生成时间：{report['generated_at']}，生成人：{report['generated_by']}")
    lines.append(
        f"- 合规分：**{report['compliance_score']} / 100**（口径 `{report['score_formula']}`，"
        f"{run['rules_passed']}/{run['rules_evaluated']} 条规则零命中）"
    )
    lines.append("")
    lines.append("## 1. 违规总览")
    lines.append("")
    lines.append("| 严重度 | 条数 |")
    lines.append("|---|---|")
    for key, item in report["severity"].items():
        lines.append(f"| {item['label']} | {item['count']} |")
    lines.append(f"| **合计** | **{report['totals']['violations']}** |")
    lines.append("")
    lines.append(
        f"状态：待整改 {report['totals']['open']}、已豁免 {report['totals']['exception']}、"
        f"已修复 {report['totals']['fixed']}。"
    )
    lines.append("")
    lines.append("## 2. 策略命中")
    lines.append("")
    lines.append("| 策略 | 标题 | 严重度 | 命中 | 待整改 | 已豁免 |")
    lines.append("|---|---|---|---|---|---|")
    for row in report["policies"]:
        lines.append(
            f"| {row['code']} | {row['title']} | {SEVERITY_LABELS.get(row['severity'], row['severity'])} "
            f"| {row['total']} | {row['open']} | {row['exception']} |"
        )
    lines.append("")
    lines.append("## 3. 命名空间分布")
    lines.append("")
    lines.append("| 命名空间 | 违规 | 待整改 | 已豁免 | 已修复 |")
    lines.append("|---|---|---|---|---|")
    for row in report["namespaces"]:
        lines.append(
            f"| {row['namespace']} | {row['total']} | {row['open']} | {row['exception']} | {row['fixed']} |"
        )
    lines.append("")
    lines.append("## 4. 超配额热点（配额引擎真实聚合）")
    lines.append("")
    if report["quota_hotspots"]:
        lines.append("| 命名空间 | 维度 | 已用 | 阈值 | 阈值来源 | 超标 |")
        lines.append("|---|---|---|---|---|---|")
        for row in report["quota_hotspots"]:
            lines.append(
                f"| {row['namespace']} | {row['metric']} | {row['used']} | {row['threshold']} "
                f"| {row['source']} | {row['over_pct']}% |"
            )
    else:
        lines.append("本轮未发现超配额命名空间。")
    lines.append("")
    lines.append("## 5. 豁免情况")
    lines.append("")
    for key, item in report["exemptions"]["by_status"].items():
        lines.append(f"- {item['label']}：{item['count']}")
    lines.append("")
    lines.append("## 6. 严重违规证据样例")
    lines.append("")
    if report["critical_samples"]:
        for sample in report["critical_samples"]:
            lines.append(
                f"- `{sample['code']}` {sample['namespace']}/{sample['resource']}："
                f"{sample['evidence_path']} 实际={sample['actual']!r} 期望={sample['expected']!r}"
            )
    else:
        lines.append("本轮没有待整改的严重违规。")
    lines.append("")
    lines.append("> 数据说明：全部为仓库内合成 K8s 清单，未连接真实集群；")
    lines.append("> 修复建议为 patch 片段，需业务团队在 GitOps 仓库合入后重跑评估复核。")
    return "\n".join(lines)

"""评估运行 / 违规 / 修复建议的请求与序列化模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

_SEVERITY_LABEL = {"low": "低", "medium": "中", "high": "高", "critical": "严重"}


class RunCreateRequest(BaseModel):
    bundle_id: str
    policy_ids: list[str] | None = None


class ViolationStatusRequest(BaseModel):
    status: str = Field(pattern="^(open|exception|fixed)$")
    note: str = Field(default="", max_length=500)


class RemediationRequest(BaseModel):
    note: str = Field(default="", max_length=500)


def serialize_run(run: Any, *, detail: bool = False) -> dict[str, Any]:
    from src.constants.enums import RUN_STATUS_LABELS, SEVERITY_ORDER
    from src.schemas.common import iso

    passed = max(0, (run.rules_evaluated or 0) - (run.rules_failed if hasattr(run, "rules_failed") else 0))
    payload: dict[str, Any] = {
        "id": str(run.id),
        "run_key": run.run_key,
        "bundle_id": str(run.bundle_id),
        "status": run.status,
        "status_label": RUN_STATUS_LABELS.get(run.status, run.status),
        "rules_evaluated": run.rules_evaluated,
        "rules_passed": run.rules_passed,
        "rules_failed": max(0, (run.rules_evaluated or 0) - (run.rules_passed or 0)),
        "docs_evaluated": run.docs_evaluated,
        "violation_count": run.violation_count,
        "triggered_by": run.triggered_by,
        "scope": run.scope_json or [],
        "error_message": run.error_message,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
    }
    if detail:
        payload["severity_order"] = SEVERITY_ORDER
        payload["passed"] = passed
    return payload


def serialize_violation(violation: Any, *, include_evidence: bool = False) -> dict[str, Any]:
    from src.constants.enums import (
        QUOTA_RULE_TITLES,
        VIOLATION_STATUS_LABELS,
        PolicySeverity,
    )
    from src.schemas.common import iso

    payload: dict[str, Any] = {
        "id": str(violation.id),
        "run_id": str(violation.run_id),
        "policy_id": violation.policy_id,
        "rule_code": violation.rule_code,
        "source": violation.source,
        "resource_kind": violation.resource_kind,
        "resource_name": violation.resource_name,
        "namespace": violation.namespace,
        "severity": violation.severity,
        "severity_label": _SEVERITY_LABEL.get(violation.severity, violation.severity),
        "status": violation.status,
        "status_label": VIOLATION_STATUS_LABELS.get(violation.status, violation.status),
        "owner_team": violation.owner_team,
        "created_at": iso(violation.created_at),
        "rule_title": QUOTA_RULE_TITLES.get(violation.rule_code, ""),
    }
    if include_evidence:
        payload["evidence"] = violation.evidence_json or {}
    return payload


def serialize_advice(advice: Any) -> dict[str, Any]:
    from src.schemas.common import iso

    return {
        "id": str(advice.id),
        "violation_id": str(advice.violation_id),
        "patch_yaml": advice.patch_yaml,
        "impact": advice.impact or {},
        "effort_level": advice.effort_level,
        "generated_by": advice.generated_by,
        "created_at": iso(advice.created_at),
    }

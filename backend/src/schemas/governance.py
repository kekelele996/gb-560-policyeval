"""豁免与合规报告请求/序列化模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExemptionCreateRequest(BaseModel):
    violation_id: str
    reason: str = Field(min_length=5, max_length=1000)
    expires_at: datetime | None = None


class ExemptionDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=500)


def serialize_exemption(exemption: Any, *, policy: Any = None, violation: Any = None) -> dict[str, Any]:
    from src.constants.enums import EXEMPTION_STATUS_LABELS
    from src.schemas.common import iso

    payload: dict[str, Any] = {
        "id": str(exemption.id),
        "policy_id": str(exemption.policy_id),
        "policy_code": policy.code if policy else None,
        "policy_title": policy.title if policy else None,
        "severity": policy.severity if policy else None,
        "namespace": exemption.namespace,
        "resource_name": exemption.resource_name,
        "reason": exemption.reason,
        "requested_by": exemption.requested_by,
        "approved_by": exemption.approved_by,
        "status": exemption.status,
        "status_label": EXEMPTION_STATUS_LABELS.get(exemption.status, exemption.status),
        "expires_at": iso(exemption.expires_at),
        "decided_at": iso(exemption.decided_at),
        "decision_note": exemption.decision_note,
        "created_at": iso(exemption.created_at),
    }
    if violation is not None:
        payload["violation_id"] = str(violation.id)
        payload["violation_status"] = violation.status
    return payload

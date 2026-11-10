"""豁免与合规报告 controller。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.models.user import User
from src.schemas.common import page_params, paginated
from src.schemas.governance import (
    ExemptionCreateRequest,
    ExemptionDecisionRequest,
    serialize_exemption,
)
from src.services import audit_service, exemption_service, report_service
from src.utils.errors import AppError


def list_exemptions(
    db: Session,
    user: User,
    *,
    page: int | None,
    page_size: int | None,
    status: str | None,
    namespace: str | None,
) -> dict:
    page, page_size = page_params(page, page_size)
    rows, total = exemption_service.list_exemptions(
        db,
        user=user,
        status=status,
        namespace=namespace,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    from src.models.violation import Violation

    items = []
    for exemption, policy in rows:
        violation = (
            db.query(Violation)
            .filter(Violation.policy_id == exemption.policy_id)
            .filter(Violation.namespace == exemption.namespace)
            .filter(Violation.resource_name == exemption.resource_name)
            .order_by(Violation.created_at.desc())
            .first()
        )
        items.append(serialize_exemption(exemption, policy=policy, violation=violation))
    return paginated(items, total, page, page_size)


def exemption_summary(db: Session, user: User) -> dict:
    return exemption_service.summary(db, user)


def request_exemption(
    request: Request, payload: ExemptionCreateRequest, db: Session, user: User
) -> dict:
    exemption = exemption_service.request_exemption(db, payload, user)
    audit_service.record(
        db,
        action="exemptions.request",
        entity_type="Exemption",
        entity_id=str(exemption.id),
        actor=user,
        payload={"namespace": exemption.namespace, "resource": exemption.resource_name},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"exemption": serialize_exemption(exemption)}


def decide_exemption(
    request: Request,
    exemption_id: str,
    payload: ExemptionDecisionRequest,
    db: Session,
    user: User,
) -> dict:
    exemption = exemption_service.get_exemption(db, exemption_id)
    exemption = exemption_service.decide(db, exemption, payload.decision, payload.note, user)
    audit_service.record(
        db,
        action="exemptions.decide",
        entity_type="Exemption",
        entity_id=str(exemption.id),
        actor=user,
        payload={
            "decision": payload.decision,
            "status": exemption.status,
            "note": payload.note,
            "namespace": exemption.namespace,
        },
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"exemption": serialize_exemption(exemption)}


def compliance_report(db: Session, user: User, run_id: str | None) -> dict:
    return report_service.build(db, user=user, run_id=run_id)


def export_report(db: Session, user: User, run_id: str | None) -> dict:
    report = report_service.build(db, user=user, run_id=run_id)
    markdown = report_service.export_markdown(report)
    return {
        "filename": f"policyeval-compliance-{report['run']['id'][:8]}.md",
        "markdown": markdown,
        "compliance_score": report["compliance_score"],
    }

"""豁免与合规报告路由（/exemptions、/reports）。"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import governance_controller
from src.middlewares.auth import get_current_user
from src.middlewares.rbac import require
from src.middlewares.rate_limit import rate_limit
from src.models.user import User
from src.schemas.governance import ExemptionCreateRequest, ExemptionDecisionRequest

router = APIRouter(tags=["governance"])


@router.get("/exemptions")
def list_exemptions(
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    status: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return governance_controller.list_exemptions(
        db, user, page=page, page_size=page_size, status=status, namespace=namespace
    )


@router.get("/exemptions/summary")
def exemption_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return governance_controller.exemption_summary(db, user)


@router.post("/exemptions", dependencies=[rate_limit("write")])
def request_exemption(
    request: Request,
    payload: ExemptionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("exemptions:request")),
) -> dict:
    return governance_controller.request_exemption(request, payload, db, user)


@router.post("/exemptions/{exemption_id}/decision", dependencies=[rate_limit("write")])
def decide_exemption(
    request: Request,
    exemption_id: str,
    payload: ExemptionDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("exemptions:approve")),
) -> dict:
    return governance_controller.decide_exemption(request, exemption_id, payload, db, user)


@router.get("/reports/compliance")
def compliance_report(
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require("report:read")),
) -> dict:
    return governance_controller.compliance_report(db, user, run_id)


@router.get("/reports/compliance/export", dependencies=[rate_limit("write")])
def export_report(
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require("report:read")),
) -> Response:
    payload = governance_controller.export_report(db, user, run_id)
    return Response(
        content=payload["markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="{payload["filename"]}"'},
    )

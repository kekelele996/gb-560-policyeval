"""评估运行 / 违规 / 整改建议路由（/runs、/violations）。"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import evaluation_controller
from src.middlewares.auth import get_current_user
from src.middlewares.rbac import require
from src.middlewares.rate_limit import rate_limit
from src.models.user import User
from src.schemas.evaluation import RemediationRequest, RunCreateRequest, ViolationStatusRequest

router = APIRouter(tags=["evaluation"])


@router.get("/runs")
def list_runs(
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return evaluation_controller.list_runs(db, page, page_size)


@router.post("/runs", dependencies=[rate_limit("write")])
def create_run(
    request: Request,
    payload: RunCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("runs:trigger")),
) -> dict:
    return evaluation_controller.create_run(request, payload, db, user)


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return evaluation_controller.get_run(db, run_id)


@router.post("/runs/{run_id}/retry", dependencies=[rate_limit("write")])
def retry_run(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require("runs:retry")),
) -> dict:
    return evaluation_controller.retry_run(request, run_id, db, user)


@router.post("/runs/{run_id}/execute", dependencies=[rate_limit("write")])
def execute_run(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require("runs:retry")),
) -> dict:
    return evaluation_controller.execute_run(request, run_id, db, user)


@router.get("/violations")
def list_violations(
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    run_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    policy_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return evaluation_controller.list_violations(
        db,
        user,
        page=page,
        page_size=page_size,
        run_id=run_id,
        severity=severity,
        namespace=namespace,
        status=status,
        source=source,
        policy_id=policy_id,
        keyword=keyword,
    )


@router.get("/violations/summary")
def violation_summary(
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return evaluation_controller.violation_summary(db, user, run_id)


@router.get("/violations/{violation_id}")
def get_violation(
    violation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return evaluation_controller.get_violation(db, user, violation_id)


@router.patch("/violations/{violation_id}/status", dependencies=[rate_limit("write")])
def update_violation_status(
    request: Request,
    violation_id: str,
    payload: ViolationStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("violations:update_status")),
) -> dict:
    return evaluation_controller.update_violation_status(request, db, user, violation_id, payload)


@router.post("/violations/{violation_id}/remediation", dependencies=[rate_limit("write")])
def generate_remediation(
    request: Request,
    violation_id: str,
    payload: RemediationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("violations:remediation")),
) -> dict:
    return evaluation_controller.generate_remediation(request, db, user, violation_id, payload)


@router.get("/violations/{violation_id}/remediation")
def get_remediation(
    violation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return evaluation_controller.get_remediation(db, user, violation_id)

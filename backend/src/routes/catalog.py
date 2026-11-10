"""清单包 / 策略路由（/bundles、/policies）。"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import catalog_controller
from src.middlewares.auth import get_current_user
from src.middlewares.rbac import require
from src.middlewares.rate_limit import rate_limit
from src.models.user import User
from src.schemas.catalog import (
    BundleImportRequest,
    DryRunRequest,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    PolicyValidateRequest,
)

router = APIRouter(tags=["catalog"])


# ---------------------------------------------------------------- bundles ----


@router.get("/bundles")
def list_bundles(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return catalog_controller.list_bundles(db)


@router.post("/bundles", dependencies=[rate_limit("write")])
def import_bundle(
    request: Request,
    payload: BundleImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("bundles:import")),
) -> dict:
    return catalog_controller.import_bundle(request, payload, db, user)


@router.get("/bundles/{bundle_id}")
def get_bundle(bundle_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return catalog_controller.get_bundle(db, bundle_id)


@router.get("/bundles/{bundle_id}/doc")
def get_bundle_doc(
    bundle_id: str,
    kind: str = Query(...),
    name: str = Query(...),
    namespace: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return catalog_controller.get_bundle_doc(db, bundle_id, kind, name, namespace)


# --------------------------------------------------------------- policies ----


@router.get("/policies")
def list_policies(
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return catalog_controller.list_policies(db, enabled)


@router.get("/policies/options")
def policy_options(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    from src.controllers import evaluation_controller

    return evaluation_controller.policy_options(db)


@router.post("/policies/validate")
def validate_policy(
    body: PolicyValidateRequest, user: User = Depends(require("policies:validate"))
) -> dict:
    return catalog_controller.validate(body)


@router.post("/policies", dependencies=[rate_limit("write")])
def create_policy(
    request: Request,
    payload: PolicyCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("policies:write")),
) -> dict:
    return catalog_controller.create_policy(request, payload, db, user)


@router.get("/policies/{policy_id}")
def get_policy(policy_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return catalog_controller.get_policy(db, policy_id)


@router.put("/policies/{policy_id}", dependencies=[rate_limit("write")])
def update_policy(
    request: Request,
    policy_id: str,
    payload: PolicyUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("policies:write")),
) -> dict:
    return catalog_controller.update_policy(request, policy_id, payload, db, user)


@router.post("/policies/{policy_id}/dry-run", dependencies=[rate_limit("write")])
def dry_run_policy(
    request: Request,
    policy_id: str,
    body: DryRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require("policies:validate")),
) -> dict:
    return catalog_controller.dry_run(request, policy_id, body, db, user)

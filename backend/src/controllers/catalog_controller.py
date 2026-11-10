"""清单包与策略 controller。"""
from __future__ import annotations

import yaml
from fastapi import Request
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.models.user import User
from src.schemas.catalog import (
    BundleImportRequest,
    DryRunRequest,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    PolicyValidateRequest,
    serialize_bundle,
    serialize_policy,
)
from src.services import audit_service, bundle_service, policy_service
from src.utils.errors import AppError


def list_bundles(db: Session) -> dict:
    rows = bundle_service.list_bundles(db)
    return {"items": [serialize_bundle(row) for row in rows], "total": len(rows)}


def get_bundle(db: Session, bundle_id: str) -> dict:
    bundle = bundle_service.get_bundle(db, bundle_id)
    tree = bundle.parsed_tree or []
    return {
        "bundle": serialize_bundle(bundle, include_tree=True),
        "tree_groups": bundle_service.tree_grouped(tree),
        "doc_count": bundle.doc_count,
        "namespace_count": bundle.namespace_count,
    }


def get_bundle_doc(db: Session, bundle_id: str, kind: str, name: str, namespace: str | None = None) -> dict:
    bundle = bundle_service.get_bundle(db, bundle_id)
    docs = bundle_service.load_docs(bundle)
    for doc in docs:
        metadata = doc.get("metadata") or {}
        if str(doc.get("kind")) != kind or str(metadata.get("name")) != name:
            continue
        if namespace and str(metadata.get("namespace") or "") not in ("", namespace):
            continue
        return {
            "kind": kind,
            "name": name,
            "namespace": str(metadata.get("namespace") or ""),
            "doc_yaml": yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        }
    raise AppError(codes.NOT_FOUND, "清单文档不存在", f"{kind}/{namespace}/{name}")


def import_bundle(request: Request, payload: BundleImportRequest, db: Session, user: User) -> dict:
    bundle = bundle_service.import_bundle(db, payload, user)
    audit_service.record(
        db,
        action="bundles.import",
        entity_type="ManifestBundle",
        entity_id=str(bundle.id),
        actor=user,
        payload={"name": bundle.name, "docs": bundle.doc_count, "files": bundle.file_count},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"bundle": serialize_bundle(bundle, include_tree=True)}


def list_policies(db: Session, enabled: bool | None = None) -> dict:
    rows = policy_service.list_policies(db, enabled=enabled)
    return {"items": [serialize_policy(row) for row in rows], "total": len(rows)}


def get_policy(db: Session, policy_id: str) -> dict:
    policy = policy_service.get_policy(db, policy_id)
    return {"policy": serialize_policy(policy)}


def validate(body: PolicyValidateRequest) -> dict:
    return policy_service.validate_dsl(body.dsl_text)


def create_policy(request: Request, payload: PolicyCreateRequest, db: Session, user: User) -> dict:
    policy = policy_service.create_policy(db, payload, user)
    audit_service.record(
        db,
        action="policies.create",
        entity_type="PolicyRule",
        entity_id=str(policy.id),
        actor=user,
        payload={"code": policy.code, "severity": policy.severity, "kind": policy.kind},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"policy": serialize_policy(policy)}


def update_policy(
    request: Request, policy_id: str, payload: PolicyUpdateRequest, db: Session, user: User
) -> dict:
    policy = policy_service.get_policy(db, policy_id)
    policy = policy_service.update_policy(db, policy, payload, user)
    audit_service.record(
        db,
        action="policies.update",
        entity_type="PolicyRule",
        entity_id=str(policy.id),
        actor=user,
        payload={"code": policy.code, "version": policy.version},
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return {"policy": serialize_policy(policy)}


def dry_run(request: Request, policy_id: str, body: DryRunRequest, db: Session, user: User) -> dict:
    policy = policy_service.get_policy(db, policy_id)
    result = policy_service.dry_run(db, policy, body.bundle_id)
    audit_service.record(
        db,
        action="policies.dry_run",
        entity_type="PolicyRule",
        entity_id=str(policy.id),
        actor=user,
        payload={
            "code": policy.code,
            "bundle": result.get("bundle_name"),
            "violation_count": result.get("violation_count"),
        },
        ip=getattr(request.state, "client_ip", ""),
        trace_id=getattr(request.state, "trace_id", ""),
    )
    return result

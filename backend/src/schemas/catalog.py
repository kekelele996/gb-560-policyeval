"""清单包与策略规则请求/响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.constants.enums import PolicySeverity


class BundleImportRequest(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    source: str = Field(default="gitops", pattern="^(gitops|upload)$")
    cluster: str = Field(default="", max_length=80)
    k8s_version: str = Field(default="", max_length=40)
    file_count: int = Field(default=1, ge=1, le=500)
    yaml_text: str = Field(min_length=1, max_length=2_000_000)


class PolicyCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=2, max_length=200)
    severity: str = Field(default="medium")
    kind: str = Field(default="Deployment")
    dsl_text: str = Field(min_length=1, max_length=4000)
    description: str = Field(default="", max_length=500)
    enabled: bool = True

    def validate_enums(self) -> None:
        from src.constants.enums import RuleKind

        if self.severity not in PolicySeverity.ALL:
            raise ValueError(f"severity 必须是 {PolicySeverity.ALL}")
        if self.kind not in RuleKind.ALL:
            raise ValueError(f"kind 必须是 {RuleKind.ALL}")


class PolicyUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    severity: str | None = None
    kind: str | None = None
    dsl_text: str | None = Field(default=None, min_length=1, max_length=4000)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class PolicyValidateRequest(BaseModel):
    dsl_text: str = Field(min_length=1, max_length=4000)


class DryRunRequest(BaseModel):
    bundle_id: str


def serialize_policy(policy: Any, *, include_ast: bool = True) -> dict[str, Any]:
    from src.schemas.common import iso

    payload: dict[str, Any] = {
        "id": str(policy.id),
        "code": policy.code,
        "title": policy.title,
        "severity": policy.severity,
        "kind": policy.kind,
        "dsl_text": policy.dsl_text,
        "enabled": policy.enabled,
        "version": policy.version,
        "description": policy.description,
        "created_by": policy.created_by,
        "created_at": iso(policy.created_at),
        "updated_at": iso(policy.updated_at),
        "parse_error": policy.parse_error_json,
        "parsed": policy.ast_json is not None,
    }
    if include_ast and policy.ast_json:
        payload["ast_json"] = policy.ast_json
        payload["ast_summary"] = (policy.ast_json or {}).get("summary")
    else:
        payload["ast_summary"] = (policy.ast_json or {}).get("summary") if policy.ast_json else None
    return payload


def serialize_bundle(bundle: Any, *, include_tree: bool = False) -> dict[str, Any]:
    from src.schemas.common import iso

    payload: dict[str, Any] = {
        "id": str(bundle.id),
        "name": bundle.name,
        "source": bundle.source,
        "cluster": bundle.cluster,
        "k8s_version": bundle.k8s_version,
        "file_count": bundle.file_count,
        "doc_count": bundle.doc_count,
        "namespace_count": bundle.namespace_count,
        "imported_by": bundle.imported_by,
        "imported_at": iso(bundle.imported_at),
        "warnings": bundle.warnings or [],
    }
    if include_tree:
        payload["parsed_tree"] = bundle.parsed_tree or []
        payload["raw_yaml"] = bundle.raw_yaml
    return payload

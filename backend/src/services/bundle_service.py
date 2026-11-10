"""清单包服务：多文档 YAML 真实解析 -> 文档树 -> 落库。

Parse 用 PyYAML safe_load_all；语法错误返回行/列（MarkedYAMLError）。
后续评估同样是重新 safe_load_all(bundle.raw_yaml)，不做二进制造假。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import yaml
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import BundleSource
from src.models.base import new_id
from src.models.manifest_bundle import ManifestBundle
from src.models.user import User
from src.schemas.catalog import BundleImportRequest
from src.utils.errors import AppError

WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet", "Pod", "Job", "ReplicaSet")


def parse_yaml_text(yaml_text: str) -> list[dict[str, Any]]:
    """解析多文档 YAML；YAML 语法错误抛 BUNDLE_PARSE_ERROR（带行列）。"""
    try:
        documents = list(yaml.safe_load_all(yaml_text))
    except yaml.MarkedYAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        raise AppError(
            codes.BUNDLE_PARSE_ERROR,
            "清单 YAML 解析失败",
            str(exc),
            extra={
                "line": (mark.line + 1) if mark else None,
                "column": (mark.column + 1) if mark else None,
                "problem": getattr(exc, "problem", str(exc)),
            },
        ) from exc
    except yaml.YAMLError as exc:  # pragma: no cover - 兜底
        raise AppError(codes.BUNDLE_PARSE_ERROR, "清单 YAML 解析失败", str(exc)) from exc
    docs: list[dict[str, Any]] = []
    for document in documents:
        if isinstance(document, dict):
            docs.append(document)
        elif document is None:
            continue
        else:
            raise AppError(
                codes.BUNDLE_PARSE_ERROR,
                "清单文档必须是映射（kind/metadata/spec）",
                f"got {type(document).__name__}",
            )
    if not docs:
        raise AppError(codes.BUNDLE_PARSE_ERROR, "清单里没有任何 K8s 文档", "empty document set")
    missing = [index for index, doc in enumerate(docs) if not doc.get("kind")]
    if missing:
        raise AppError(
            codes.BUNDLE_PARSE_ERROR,
            "存在缺少 kind 的文档",
            f"doc indexes={missing[:5]}",
            extra={"doc_indexes": missing[:10]},
        )
    return docs


def build_tree(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """文档树：每个文档一行 kind/name/namespace + 关键摘要。"""
    tree: list[dict[str, Any]] = []
    for doc in docs:
        metadata = doc.get("metadata") or {}
        kind = str(doc.get("kind"))
        namespace = str(metadata.get("namespace") or (metadata.get("name") if kind == "Namespace" else ""))
        entry: dict[str, Any] = {
            "kind": kind,
            "name": str(metadata.get("name") or "<unnamed>"),
            "namespace": namespace,
        }
        if kind in WORKLOAD_KINDS:
            spec = doc.get("spec") or {}
            if kind == "Pod":
                pod_spec = spec
            else:
                pod_spec = (spec.get("template") or {}).get("spec") or {}
            containers = pod_spec.get("containers") or []
            entry["replicas"] = spec.get("replicas")
            entry["container_count"] = len([c for c in containers if isinstance(c, dict)])
            entry["images"] = [
                str((c or {}).get("image") or "")
                for c in containers
                if isinstance(c, dict)
            ][:4]
        if kind in ("ResourceQuota", "LimitRange"):
            entry["spec_keys"] = list((doc.get("spec") or {}).keys())
        tree.append(entry)
    return tree


def _namespace_count(tree: list[dict[str, Any]]) -> int:
    return len({item["namespace"] for item in tree if item["namespace"]})


def import_bundle(db: Session, payload: BundleImportRequest, user: User) -> ManifestBundle:
    existing = db.query(ManifestBundle).filter(ManifestBundle.name == payload.name).one_or_none()
    if existing is not None:
        raise AppError(
            codes.CONFLICT,
            "同名清单包已存在",
            f"bundle name={payload.name}",
            extra={"bundle_id": str(existing.id)},
        )
    docs = parse_yaml_text(payload.yaml_text)
    tree = build_tree(docs)
    warnings: list[str] = []
    namespaces = {item["namespace"] for item in tree if item["namespace"]}
    missing_ns = [d for d in docs if d.get("kind") != "Namespace" and not (d.get("metadata") or {}).get("namespace")]
    if missing_ns:
        warnings.append(f"{len(missing_ns)} 个文档缺 metadata.namespace，评估时按 default 处理")
    bundle = ManifestBundle(
        id=new_id(),
        name=payload.name,
        source=payload.source if payload.source in BundleSource.ALL else BundleSource.UPLOAD,
        cluster=payload.cluster,
        k8s_version=payload.k8s_version,
        file_count=payload.file_count,
        doc_count=len(docs),
        namespace_count=len(namespaces),
        parsed_tree=tree,
        raw_yaml=payload.yaml_text,
        warnings=warnings,
        imported_by=user.email,
        imported_at=datetime.utcnow(),
    )
    db.add(bundle)
    db.flush()
    return bundle


def create_seed_bundle(
    db: Session,
    *,
    name: str,
    yaml_text: str,
    docs: list[dict[str, Any]],
    cluster: str,
    k8s_version: str,
    file_count: int,
    imported_by: str,
) -> ManifestBundle:
    """seed 用：按 name 幂等 upsert（已存在不覆盖用户改动）。"""
    existing = db.query(ManifestBundle).filter(ManifestBundle.name == name).one_or_none()
    if existing is not None:
        return existing
    tree = build_tree(docs)
    bundle = ManifestBundle(
        id=new_id(),
        name=name,
        source="gitops",
        cluster=cluster,
        k8s_version=k8s_version,
        file_count=file_count,
        doc_count=len(docs),
        namespace_count=_namespace_count(tree),
        parsed_tree=tree,
        raw_yaml=yaml_text,
        warnings=[],
        imported_by=imported_by,
        imported_at=datetime.utcnow(),
    )
    db.add(bundle)
    db.flush()
    return bundle


def list_bundles(db: Session) -> list[ManifestBundle]:
    return db.query(ManifestBundle).order_by(ManifestBundle.imported_at.desc()).all()


def get_bundle(db: Session, bundle_id: str) -> ManifestBundle:
    bundle = db.get(ManifestBundle, bundle_id)
    if bundle is None:
        raise AppError(codes.NOT_FOUND, "清单包不存在", f"bundle_id={bundle_id}")
    return bundle


def load_docs(bundle: ManifestBundle) -> list[dict[str, Any]]:
    return parse_yaml_text(bundle.raw_yaml)


def tree_grouped(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 namespace 分组的文档树，给前端左栏导航。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in tree:
        groups.setdefault(item["namespace"] or "(cluster)", []).append(item)
    return [
        {"namespace": namespace, "docs": docs, "doc_count": len(docs)}
        for namespace, docs in sorted(groups.items())
    ]

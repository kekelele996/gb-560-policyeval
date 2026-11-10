"""核心算法 1 的求值侧：在手写解析器产出的 AST 上对 PyYAML 文档树求值。

口径
----
- 路径展开：`[*]` / `[]` 通配符展开成多个叶子，每条叶子独立求值；
  `all/any` 在子表达式层面短路，`not` 取反。
- 缺失字段 -> 该叶子 false 并记 `missing_field` warning（计划口径）。
- 类型不匹配 -> false 并记 `type_mismatch`（例如把字符串当数字比较）；
  K8s quantity 字符串（"500m" / "1Gi"）在与数字比较时做一次受控折算并记
  `coerced_quantity`，不是类型错误。
- 量词语义：compare / hasKey / count 对通配符展开采用**全称**语义（每个叶子都要满足），
  startsWith / matches 采用**存在**语义（任一叶子命中即成立，用于「任意容器使用 latest」
  这类检测）；not(...) 反转子表达式。该口径写入 README 与本文件头。
- 证据：每条违规带 evidence_path（叶子路径）+ actual_value + expected，
  前端只展示本模块的输出，不做任何判定。

禁止使用 eval()/exec()：本模块只做显式 AST 遍历。
"""
from __future__ import annotations

import re
from typing import Any

from src.config.settings import settings
from src.constants.enums import QUOTA_RULE_CODE_OVER  # noqa: F401 - 供上层引用
from src.services.quota import parse_quantity


# ------------------------------------------------------------------ 路径展开 ----

def _render_parts(parts: list[str]) -> str:
    out = ""
    for part in parts:
        if part.startswith("["):
            out += part
        elif out:
            out += "." + part
        else:
            out = part
    return out


def _missing(parts: list[str], note: str) -> dict[str, Any]:
    return {
        "parts": parts,
        "value": None,
        "exists": False,
        "note": note,
        "path": _render_parts(parts),
    }


def resolve_path(doc: Any, path: dict[str, Any]) -> list[dict[str, Any]]:
    """按路径展开文档树，返回叶子列表（含不存在的叶子）。"""
    current: list[dict[str, Any]] = [
        {"parts": [], "value": doc, "exists": True, "note": None, "path": ""}
    ]
    for segment in path.get("segments") or []:
        kind = segment.get("kind")
        next_items: list[dict[str, Any]] = []
        for item in current:
            value = item["value"]
            if kind == "field":
                name = segment["name"]
                parts = item["parts"] + [name]
                if not item["exists"]:
                    next_items.append(_missing(parts, item["note"] or "missing_field"))
                elif isinstance(value, dict) and name in value:
                    next_items.append(
                        {
                            "parts": parts,
                            "value": value[name],
                            "exists": True,
                            "note": None,
                            "path": _render_parts(parts),
                        }
                    )
                else:
                    next_items.append(_missing(parts, "missing_field"))
            elif kind == "wildcard":
                if not item["exists"]:
                    next_items.append(_missing(item["parts"] + ["[]"], item["note"] or "missing_field"))
                elif isinstance(value, list):
                    if not value:
                        next_items.append(_missing(item["parts"] + ["[]"], "empty_list"))
                    else:
                        for index, sub in enumerate(value):
                            parts = item["parts"] + [f"[{index}]"]
                            next_items.append(
                                {
                                    "parts": parts,
                                    "value": sub,
                                    "exists": True,
                                    "note": None,
                                    "path": _render_parts(parts),
                                }
                            )
                else:
                    next_items.append(_missing(item["parts"] + ["[]"], "not_a_list"))
            elif kind == "index":
                index = int(segment.get("index", 0))
                parts = item["parts"] + [f"[{index}]"]
                if not item["exists"]:
                    next_items.append(_missing(parts, item["note"] or "missing_field"))
                elif isinstance(value, list) and 0 <= index < len(value):
                    next_items.append(
                        {
                            "parts": parts,
                            "value": value[index],
                            "exists": True,
                            "note": None,
                            "path": _render_parts(parts),
                        }
                    )
                elif isinstance(value, list):
                    next_items.append(_missing(parts, "index_out_of_range"))
                else:
                    next_items.append(_missing(parts, "not_a_list"))
            else:  # pragma: no cover - 解析器保证不会出现
                next_items.append(_missing(item["parts"], "bad_segment"))
        current = next_items
    return current


# ------------------------------------------------------------------- 值比较 ----

def _type_mismatch(actual: Any, expected_kind: str) -> str:
    return f"type_mismatch: actual={type(actual).__name__} expected={expected_kind}"


def _compare_value(actual: Any, expected: dict[str, Any], op: str) -> tuple[bool, str | None]:
    """返回 (passed, note)。note=None 表示类型正常。"""
    kind = expected.get("kind")
    wanted = expected.get("value")

    if kind == "null":
        if actual is None:
            return (op == "=="), None
        if op == "==":
            return False, _type_mismatch(actual, "null")
        return False, _type_mismatch(actual, "null")

    if kind == "bool":
        if not isinstance(actual, bool):
            return False, _type_mismatch(actual, "bool")
        passed = actual == bool(wanted)
        return (passed if op == "==" else not passed), None

    if kind == "string":
        if not isinstance(actual, str):
            return False, _type_mismatch(actual, "string")
        if op == "==":
            return actual == wanted, None
        if op == "!=":
            return actual != wanted, None
        return False, "operator_not_supported_for_string"

    # number
    if isinstance(actual, bool):
        return False, _type_mismatch(actual, "number")
    note: str | None = None
    actual_number: float
    if isinstance(actual, (int, float)):
        actual_number = float(actual)
    elif isinstance(actual, str):
        parsed = parse_quantity(actual)
        if parsed["warning"]:
            return False, _type_mismatch(actual, "number")
        actual_number = float(parsed["value"])
        note = "coerced_quantity"
    else:
        return False, _type_mismatch(actual, "number")
    if op == "==":
        return actual_number == float(wanted), note
    if op == "!=":
        return actual_number != float(wanted), note
    if op == ">":
        return actual_number > float(wanted), note
    if op == ">=":
        return actual_number >= float(wanted), note
    if op == "<":
        return actual_number < float(wanted), note
    if op == "<=":
        return actual_number <= float(wanted), note
    return False, "unsupported_operator"


def _expected_display(expected: dict[str, Any]) -> Any:
    return expected.get("value")


# ------------------------------------------------------------------ AST 求值 ----

class _Collector:
    def __init__(self) -> None:
        self.leaf_results: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.evaluated_nodes = 0

    def warn(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)

    def add_leaf(self, result: dict[str, Any]) -> None:
        self.leaf_results.append(result)


def _leaf_result(
    leaf: dict[str, Any],
    *,
    expected: Any,
    op: str,
    passed: bool,
    note: str | None,
    template: str,
    negated: bool = False,
) -> dict[str, Any]:
    return {
        "template": template,
        "path": leaf["path"],
        "actual": leaf["value"] if leaf["exists"] else None,
        "exists": leaf["exists"],
        "expected": expected,
        "op": op,
        "passed": passed,
        "note": note,
        "negated": negated,
    }


def _eval_compare(node: dict[str, Any], doc: Any, ctx: _Collector, negated: bool) -> bool:
    ctx.evaluated_nodes += 1
    path = node["path"]
    op = node["op"]
    expected = node["value"]
    leaves = resolve_path(doc, path)
    all_passed = True
    for leaf in leaves:
        if not leaf["exists"]:
            ctx.warn("missing_field")
            passed = False
            note = leaf["note"] or "missing_field"
        else:
            passed, note = _compare_value(leaf["value"], expected, op)
            if note and note.startswith("type_mismatch"):
                ctx.warn("type_mismatch")
            elif note == "coerced_quantity":
                ctx.warn("coerced_quantity")
        if not passed:
            all_passed = False
        ctx.add_leaf(
            _leaf_result(
                leaf,
                expected=_expected_display(expected),
                op=op,
                passed=passed,
                note=note,
                template=path["raw"],
                negated=negated,
            )
        )
    if not leaves:
        ctx.warn("path_not_found")
        return False
    return all_passed


def _eval_has_key(node: dict[str, Any], doc: Any, ctx: _Collector, negated: bool) -> bool:
    ctx.evaluated_nodes += 1
    path = node["path"]
    leaves = resolve_path(doc, path)
    all_passed = True
    for leaf in leaves:
        passed = bool(leaf["exists"])
        if not passed:
            ctx.warn("missing_field")
        else:
            ctx.warn("present_field")
        all_passed = all_passed and passed
        ctx.add_leaf(
            _leaf_result(
                leaf,
                expected="exists",
                op="hasKey",
                passed=passed,
                note=None if passed else (leaf["note"] or "missing_field"),
                template=path["raw"],
                negated=negated,
            )
        )
    if not leaves:
        return False
    return all_passed


def _eval_count(node: dict[str, Any], doc: Any, ctx: _Collector, negated: bool) -> bool:
    ctx.evaluated_nodes += 1
    path = node["path"]
    op = node["op"]
    expected = node["value"]
    leaves = resolve_path(doc, path)
    all_passed = True
    for leaf in leaves:
        passed = False
        note: str | None = None
        count_value: int | None = None
        if not leaf["exists"]:
            note = leaf["note"] or "missing_field"
            ctx.warn("missing_field")
        elif isinstance(leaf["value"], list):
            count_value = len(leaf["value"])
            passed, note = _compare_value(count_value, expected, op)
        else:
            note = "type_mismatch: count() 需要数组"
            ctx.warn("type_mismatch")
        all_passed = all_passed and passed
        ctx.add_leaf(
            _leaf_result(
                leaf,
                expected=_expected_display(expected),
                op=f"count {op}",
                passed=passed,
                note=note,
                template=path["raw"],
                negated=negated,
            )
        )
    if not leaves:
        return False
    return all_passed


def _eval_string_fn(node: dict[str, Any], doc: Any, ctx: _Collector, negated: bool) -> bool:
    ctx.evaluated_nodes += 1
    path = node["path"]
    fn = node["fn"]
    arg = node["arg"]
    leaves = resolve_path(doc, path)
    any_passed = False
    evaluated = 0
    for leaf in leaves:
        passed = False
        note: str | None = None
        if not leaf["exists"]:
            note = leaf["note"] or "missing_field"
            ctx.warn("missing_field")
        elif not isinstance(leaf["value"], str):
            note = _type_mismatch(leaf["value"], "string")
            ctx.warn("type_mismatch")
        else:
            evaluated += 1
            if fn == "startsWith":
                passed = leaf["value"].startswith(arg)
            elif fn == "matches":
                try:
                    passed = re.fullmatch(arg, leaf["value"]) is not None
                except re.error:
                    note = "invalid_regex"
                    ctx.warn("invalid_regex")
        any_passed = any_passed or passed
        ctx.add_leaf(
            _leaf_result(
                leaf,
                expected=f"{fn}({arg!r})",
                op=fn,
                passed=passed,
                note=note,
                template=path["raw"],
                negated=negated,
            )
        )
    if not leaves or evaluated == 0:
        return False
    return any_passed


def eval_ast(
    node: dict[str, Any],
    doc: Any,
    ctx: _Collector | None = None,
    negated: bool = False,
) -> tuple[bool, _Collector]:
    """求值入口：返回 (matched, collector)。"""
    ctx = ctx or _Collector()
    node_type = node.get("type")
    if node_type == "logical":
        op = node["op"]
        if op == "not":
            child = node["args"][0]
            inner_matched, _ = eval_ast(child, doc, ctx, negated=not negated)
            return (not inner_matched), ctx
        if op == "all":
            for child in node.get("args") or []:
                matched, _ = eval_ast(child, doc, ctx, negated=negated)
                if not matched:
                    ctx.warn("short_circuit:all")
                    return False, ctx
            return True, ctx
        if op == "any":
            for child in node.get("args") or []:
                matched, _ = eval_ast(child, doc, ctx, negated=negated)
                if matched:
                    ctx.warn("short_circuit:any")
                    return True, ctx
            return False, ctx
        ctx.warn(f"unknown_logical:{op}")
        return False, ctx
    if node_type == "compare":
        return _eval_compare(node, doc, ctx, negated), ctx
    if node_type == "hasKey":
        return _eval_has_key(node, doc, ctx, negated), ctx
    if node_type == "count":
        return _eval_count(node, doc, ctx, negated), ctx
    if node_type == "stringFn":
        return _eval_string_fn(node, doc, ctx, negated), ctx
    ctx.warn(f"unknown_node:{node_type}")
    return False, ctx


# --------------------------------------------------------------- 策略级求值 ----

# PolicyRule.kind -> 适用文档 kind 集合
KIND_TARGETS: dict[str, tuple[str, ...]] = {
    "Deployment": ("Deployment",),
    "Pod": ("Pod",),
    "Namespace": ("Namespace",),
    "LimitRange": ("LimitRange", "ResourceQuota"),
}


def document_namespace(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata") or {}
    namespace = metadata.get("namespace")
    if namespace:
        return str(namespace)
    return str(metadata.get("name") or "") if doc.get("kind") == "Namespace" else "default"


def document_identity(doc: dict[str, Any]) -> tuple[str, str, str]:
    metadata = doc.get("metadata") or {}
    return (
        str(doc.get("kind") or "Unknown"),
        document_namespace(doc),
        str(metadata.get("name") or "<unnamed>"),
    )


def _resource_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    """违规对象的轻量快照：remediation 生成 patch 时用于定位容器/镜像。"""
    spec = doc.get("spec") or {}
    kind = doc.get("kind")
    pod_spec = spec if kind == "Pod" else ((spec.get("template") or {}).get("spec") or {})
    containers = []
    for item in (pod_spec.get("containers") or [])[:8]:
        if not isinstance(item, dict):
            continue
        resources = item.get("resources") or {}
        containers.append(
            {
                "name": str(item.get("name") or "<container>"),
                "image": str(item.get("image") or ""),
                "has_limits": bool((resources.get("limits") or {}).get("cpu"))
                and bool((resources.get("limits") or {}).get("memory")),
                "has_requests": bool((resources.get("requests") or {}).get("cpu")),
            }
        )
    return {
        "kind": kind,
        "namespace": document_namespace(doc),
        "name": str((doc.get("metadata") or {}).get("name") or ""),
        "replicas": spec.get("replicas"),
        "containers": containers,
        "labels": list(((doc.get("metadata") or {}).get("labels") or {}).keys())[:8],
    }


def evaluate_policy_on_docs(
    policy: dict[str, Any],
    docs: list[dict[str, Any]],
    max_docs: int | None = None,
) -> dict[str, Any]:
    """对一批文档执行单条策略，返回命中情况与违规候选（不落库）。"""
    raw_ast = policy.get("ast_json") or policy.get("ast")
    if not raw_ast:
        return {
            "evaluated_docs": 0,
            "matched_docs": 0,
            "violations": [],
            "error": "policy_has_no_ast",
        }
    # parse_dsl 的落库结构是 {ast, predicate_count, path_count, max_depth, summary}；
    # 也兼容直接传 AST 节点的调用
    if isinstance(raw_ast, dict) and raw_ast.get("type") is None and "ast" in raw_ast:
        ast = raw_ast["ast"]
        ast_summary = raw_ast.get("summary")
    else:
        ast = raw_ast
        ast_summary = policy.get("summary")
    targets = KIND_TARGETS.get(policy.get("kind"), (policy.get("kind"),))
    evaluated = 0
    matched = 0
    violations: list[dict[str, Any]] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") not in targets:
            continue
        evaluated += 1
        matched_doc, ctx = eval_ast(ast, doc)
        if matched_doc:
            matched += 1
            continue
        kind, namespace, name = document_identity(doc)
        failed_leaves = [leaf for leaf in ctx.leaf_results if not leaf["passed"]]
        warnings = [w for w in ctx.warnings if not w.startswith("short_circuit")]
        evidence = {
            "algorithm": "dsl-evaluator",
            "resource": _resource_snapshot(doc),
            "policy_code": policy.get("code"),
            "policy_title": policy.get("title"),
            "dsl": policy.get("dsl_text"),
            "ast_summary": ast_summary,
            "matched": False,
            "evaluated_leaves": len(ctx.leaf_results),
            "failed_leaves": len(failed_leaves),
            "leaf_results": failed_leaves[: settings.DSL_MAX_EVIDENCE],
            "leaf_results_truncated": len(failed_leaves) > settings.DSL_MAX_EVIDENCE,
            "warnings": warnings,
            "short_circuit": [w for w in ctx.warnings if w.startswith("short_circuit")],
        }
        violations.append(
            {
                "policy_id": policy.get("id"),
                "rule_code": policy.get("code"),
                "source": "dsl",
                "resource_kind": kind,
                "resource_name": name,
                "namespace": namespace,
                "severity": policy.get("severity", "medium"),
                "evidence": evidence,
            }
        )
        if max_docs is not None and len(violations) >= max_docs:
            break
    return {
        "evaluated_docs": evaluated,
        "matched_docs": matched,
        "violation_count": len(violations),
        "violations": violations,
    }


def dry_run_policy(policy: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any]:
    """策略编辑器「试运行」：返回命中数 + 前若干违规 evidence（不持久化）。"""
    result = evaluate_policy_on_docs(policy, docs, max_docs=200)
    preview = [
        {
            "resource_kind": item["resource_kind"],
            "resource_name": item["resource_name"],
            "namespace": item["namespace"],
            "evidence": item["evidence"],
        }
        for item in result["violations"][:5]
    ]
    return {
        "policy_code": policy.get("code"),
        "evaluated_docs": result["evaluated_docs"],
        "matched_docs": result["matched_docs"],
        "violation_count": result["violation_count"],
        "violated_docs": result["evaluated_docs"] - result["matched_docs"],
        "violations_preview": preview,
    }

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urldefrag, urlparse

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from multiverse_workflow.protocol.diagnostics import Diagnostic, DiagnosticError
from multiverse_workflow.protocol.loader import load_document
from multiverse_workflow.protocol.models import (
    AllPredicate,
    AnyPredicate,
    ArrayExpr,
    ComparisonPredicate,
    LiteralExpr,
    NotPredicate,
    ObjectExpr,
    Predicate,
    RefExpr,
    ValueExpr,
)


def validate_schema_file(
    path: Path,
    package_root: Path | None = None,
) -> tuple[dict[str, Any] | None, Diagnostic | None]:
    """Load a Draft 2020-12 schema and verify its local references.

    Schema references are resolved from the schema file's directory. The
    package root check is deliberately performed before jsonschema gets a
    chance to retrieve anything, so remote or escaping references fail closed.
    """

    root = (package_root or path.parent).resolve()
    visited: set[Path] = set()

    def visit(schema_path: Path) -> tuple[dict[str, Any] | None, Diagnostic | None]:
        resolved = schema_path.resolve()
        if resolved in visited:
            return None, None
        visited.add(resolved)
        try:
            document = load_document(resolved)
        except DiagnosticError as exc:
            return None, exc.diagnostic
        schema = document.value
        if not isinstance(schema, dict):
            return None, _schema_diagnostic(
                "SCHEMA_FILE_INVALID",
                resolved,
                "Schema 根值必须是对象。",
            )
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            return None, _schema_diagnostic(
                "SCHEMA_FILE_INVALID",
                resolved,
                "Schema 必须声明 Draft 2020-12。",
            )
        for reference in _schema_refs(schema):
            reference_path, reference_diagnostic = _resolve_schema_reference(
                resolved,
                reference,
                root,
            )
            if reference_diagnostic is not None:
                return None, reference_diagnostic
            if reference_path is not None:
                _, child_diagnostic = visit(reference_path)
                if child_diagnostic is not None:
                    return None, child_diagnostic
        return schema, None

    return visit(path)


def schema_validator(
    schema: dict[str, Any],
    schema_path: Path,
    package_root: Path | None = None,
) -> Draft202012Validator:
    root = (package_root or schema_path.parent).resolve()
    base_path = schema_path.resolve()

    def retrieve(uri: str) -> Resource[Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise LookupError(f"remote schema reference is forbidden: {uri}")
        candidate = Path(unquote(parsed.path)).resolve()
        if root not in candidate.parents and candidate != root:
            raise LookupError(f"schema reference escapes package root: {candidate}")
        try:
            document = load_document(candidate)
        except DiagnosticError as exc:
            raise LookupError(str(exc)) from exc
        if not isinstance(document.value, dict):
            raise LookupError(f"schema is not an object: {candidate}")
        return Resource.from_contents(document.value)

    registry = Registry(retrieve=retrieve)  # type: ignore[call-arg]
    registry = registry.with_resource(
        base_path.as_uri(),
        Resource.from_contents(schema),
    )
    return Draft202012Validator(schema, registry=registry)


def validate_value_expr_references(
    expression: ValueExpr,
    *,
    allowed_nodes: set[str],
    completed_nodes: set[str],
    file: str,
    pointer: str,
    allow_iteration: bool = False,
    node_output_schemas: dict[str, Path] | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    def visit(value: ValueExpr, value_pointer: str) -> None:
        if isinstance(value, RefExpr):
            diagnostic = _validate_ref(
                value.ref,
                allowed_nodes=allowed_nodes,
                completed_nodes=completed_nodes,
                allow_iteration=allow_iteration,
                file=file,
                pointer=value_pointer + "/ref",
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
                return
            parsed = _parse_reference(value.ref)
            if parsed is None or parsed[0] != "node":
                return
            node_id, json_pointer = parsed[1], parsed[2]
            schema_path = (node_output_schemas or {}).get(node_id)
            if schema_path is not None:
                schema, schema_diagnostic = validate_schema_file(schema_path)
                if schema_diagnostic is not None:
                    diagnostics.append(schema_diagnostic)
                elif schema is not None and not _schema_pointer_exists(schema, json_pointer):
                    diagnostics.append(
                        Diagnostic(
                            code="DATA_REFERENCE_MISSING",
                            file=file,
                            pointer=value_pointer + "/ref",
                            message=f"数据引用不存在：{value.ref}。",
                            suggestion="确认节点输出 Schema 和 JSON Pointer 一致。",
                        )
                    )
            return
        if isinstance(value, ObjectExpr):
            for key, child in value.object.items():
                visit(child, f"{value_pointer}/object/{_escape(key)}")
        elif isinstance(value, ArrayExpr):
            for index, child in enumerate(value.array):
                visit(child, f"{value_pointer}/array/{index}")
        elif isinstance(value, LiteralExpr):
            return

    visit(expression, pointer)
    return diagnostics


def validate_predicate_references(
    predicate: Predicate,
    *,
    allowed_nodes: set[str],
    completed_nodes: set[str],
    file: str,
    pointer: str,
    allow_iteration: bool = False,
    node_output_schemas: dict[str, Path] | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    if isinstance(predicate, ComparisonPredicate):
        diagnostics.extend(
            validate_value_expr_references(
                predicate.left,
                allowed_nodes=allowed_nodes,
                completed_nodes=completed_nodes,
                file=file,
                pointer=pointer + "/left",
                allow_iteration=allow_iteration,
                node_output_schemas=node_output_schemas,
            )
        )
        diagnostics.extend(
            validate_value_expr_references(
                predicate.right,
                allowed_nodes=allowed_nodes,
                completed_nodes=completed_nodes,
                file=file,
                pointer=pointer + "/right",
                allow_iteration=allow_iteration,
                node_output_schemas=node_output_schemas,
            )
        )
        if predicate.op == "in" and isinstance(predicate.right, LiteralExpr):
            if not isinstance(predicate.right.literal, list):
                diagnostics.append(
                    Diagnostic(
                        code="INVALID_PREDICATE",
                        file=file,
                        pointer=pointer + "/right",
                        message="in 条件的右值必须是 array。",
                    )
                )
        return diagnostics
    if isinstance(predicate, AllPredicate):
        for index, child in enumerate(predicate.all):
            diagnostics.extend(
                validate_predicate_references(
                    child,
                    allowed_nodes=allowed_nodes,
                    completed_nodes=completed_nodes,
                    file=file,
                    pointer=f"{pointer}/all/{index}",
                    allow_iteration=allow_iteration,
                    node_output_schemas=node_output_schemas,
                )
            )
    elif isinstance(predicate, AnyPredicate):
        for index, child in enumerate(predicate.any):
            diagnostics.extend(
                validate_predicate_references(
                    child,
                    allowed_nodes=allowed_nodes,
                    completed_nodes=completed_nodes,
                    file=file,
                    pointer=f"{pointer}/any/{index}",
                    allow_iteration=allow_iteration,
                    node_output_schemas=node_output_schemas,
                )
            )
    elif isinstance(predicate, NotPredicate):
        diagnostics.extend(
            validate_predicate_references(
                predicate.not_,
                allowed_nodes=allowed_nodes,
                completed_nodes=completed_nodes,
                file=file,
                pointer=pointer + "/not",
                allow_iteration=allow_iteration,
                node_output_schemas=node_output_schemas,
            )
        )
    return diagnostics


def _validate_ref(
    reference: str,
    *,
    allowed_nodes: set[str],
    completed_nodes: set[str],
    allow_iteration: bool,
    file: str,
    pointer: str,
) -> Diagnostic | None:
    parsed = _parse_reference(reference)
    if parsed is None:
        return Diagnostic(
            code="INVALID_REFERENCE",
            file=file,
            pointer=pointer,
            message=f"数据引用格式无效：{reference}。",
            suggestion="使用 input#、input#/path 或 nodes.<node_id>.output#/path。",
        )
    kind, name, json_pointer = parsed
    if kind == "input":
        return None
    if kind == "iteration":
        if not allow_iteration:
            return Diagnostic(
                code="INVALID_REFERENCE_SCOPE",
                file=file,
                pointer=pointer,
                message="当前位置不能读取 iteration 引用。",
            )
        if name == "index" and json_pointer:
            return Diagnostic(
                code="INVALID_REFERENCE",
                file=file,
                pointer=pointer,
                message="iteration.index 只能引用整个索引值。",
            )
        return None
    if name not in allowed_nodes:
        return Diagnostic(
            code="DATA_REFERENCE_MISSING",
            file=file,
            pointer=pointer,
            message=f"数据引用的节点不存在：{name}。",
            suggestion="确认 node_id 拼写并引用包内节点输出。",
        )
    if name not in completed_nodes:
        return Diagnostic(
            code="DATA_REFERENCE_UNAVAILABLE",
            file=file,
            pointer=pointer,
            message=f"节点输出尚未支配当前读取点：{name}。",
            suggestion="只引用当前路径上已完成且可确定存在的节点输出。",
        )
    return None


def _parse_reference(reference: str) -> tuple[str, str, str] | None:
    if "#" not in reference:
        return None
    root, fragment = reference.split("#", 1)
    if fragment and not fragment.startswith("/"):
        return None
    json_pointer = fragment
    if root == "input":
        return ("input", "", json_pointer)
    if root == "iteration.output":
        return ("iteration", "output", json_pointer)
    if root == "iteration.index":
        return ("iteration", "index", json_pointer)
    if root.startswith("nodes.") and root.endswith(".output"):
        node_id = root[len("nodes.") : -len(".output")]
        if node_id:
            return ("node", node_id, json_pointer)
    return None


def _schema_refs(schema: Any) -> list[str]:
    references: list[str] = []
    if isinstance(schema, dict):
        value = schema.get("$ref")
        if isinstance(value, str):
            references.append(value)
        for child in schema.values():
            references.extend(_schema_refs(child))
    elif isinstance(schema, list):
        for child in schema:
            references.extend(_schema_refs(child))
    return references


def _resolve_schema_reference(
    schema_path: Path,
    reference: str,
    package_root: Path,
) -> tuple[Path | None, Diagnostic | None]:
    path_part, _ = urldefrag(reference)
    parsed = urlparse(path_part)
    if parsed.scheme or parsed.netloc or path_part.startswith("/"):
        return None, _schema_diagnostic(
            "SCHEMA_REF_FORBIDDEN",
            schema_path,
            f"Schema 只能引用包内相对路径：{reference}。",
        )
    if not path_part:
        return None, None
    relative = Path(unquote(path_part))
    if ".." in relative.parts:
        return None, _schema_diagnostic(
            "SCHEMA_REF_FORBIDDEN",
            schema_path,
            f"Schema 引用不能包含父目录：{reference}。",
        )
    candidate = (schema_path.parent / relative).resolve()
    if package_root not in candidate.parents and candidate != package_root:
        return None, _schema_diagnostic(
            "SCHEMA_REF_FORBIDDEN",
            schema_path,
            f"Schema 引用越过包根：{reference}。",
        )
    if not candidate.is_file():
        return None, _schema_diagnostic(
            "SCHEMA_REF_NOT_FOUND",
            schema_path,
            f"Schema 引用文件不存在：{reference}。",
        )
    return candidate, None


def _schema_pointer_exists(schema: dict[str, Any], pointer: str) -> bool:
    if not pointer:
        return True
    current: Any = schema
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, dict) and token == "*":
            return True
        if isinstance(current, dict) and "properties" in current:
            properties = current["properties"]
            if isinstance(properties, dict) and token in properties:
                current = properties[token]
                continue
            if current.get("additionalProperties") is not False:
                return True
        return False
    return True


def _schema_diagnostic(code: str, path: Path, message: str) -> Diagnostic:
    return Diagnostic(code=code, file=str(path), pointer="", message=message)


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")

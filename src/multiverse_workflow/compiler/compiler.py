from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from multiverse_workflow.compiler.digests import (
    binding_digest,
    canonical_json,
    package_digest,
    package_file_manifest,
    sha256_digest,
)
from multiverse_workflow.compiler.graph import validate_graph
from multiverse_workflow.compiler.references import (
    SchemaSource,
    schema_validator,
    validate_predicate_references,
    validate_schema_file,
    validate_value_expr_references,
)
from multiverse_workflow.protocol.diagnostics import Diagnostic, DiagnosticError
from multiverse_workflow.protocol.loader import load_document
from multiverse_workflow.protocol.models import (
    BindingSet,
    CallNode,
    EndNode,
    ParallelNode,
    RepeatNode,
    Workflow,
    WorkflowNode,
    WorkflowPackage,
)

_SUPPORTED_FEATURES = {
    "core.call",
    "core.switch",
    "core.human",
    "core.nested",
    "core.workflow",
    "core.parallel",
    "core.repeat",
}

_EXECUTOR_CAPABILITIES = {
    "example.content-fixture.v1": {"content.produce@1"},
    "example.remote-content.v1": {"content.produce@1"},
    "builtin.nonempty-deliverable.v1": {"data.validate@1"},
    "builtin.human-review.v1": {"human.review@1"},
}

_EXECUTOR_DESCRIPTORS: dict[str, dict[str, Any]] = {
    "example.content-fixture.v1": {
        "adapter": "builtin",
        "capabilities": {"content.produce@1"},
        "contractVersion": "multiverse/v0.1",
        "executorVersion": "1.0.0",
        "supportsCancel": True,
        "supportsIdempotency": True,
        "supportsRecoveryQuery": True,
        "observabilityLevel": "structured",
        "permissionLevel": "enforced",
    },
    "example.remote-content.v1": {
        "adapter": "http_job",
        "capabilities": {"content.produce@1"},
        "contractVersion": "multiverse/v0.1",
        "executorVersion": "1.0.0",
        "supportsCancel": True,
        "supportsIdempotency": True,
        "supportsRecoveryQuery": True,
        "observabilityLevel": "external",
        "permissionLevel": "enforced",
    },
    "builtin.nonempty-deliverable.v1": {
        "adapter": "builtin",
        "capabilities": {"data.validate@1"},
        "contractVersion": "multiverse/v0.1",
        "executorVersion": "1.0.0",
        "supportsCancel": True,
        "supportsIdempotency": True,
        "supportsRecoveryQuery": True,
        "observabilityLevel": "structured",
        "permissionLevel": "enforced",
    },
    "builtin.human-review.v1": {
        "adapter": "human",
        "capabilities": {"human.review@1"},
        "contractVersion": "multiverse/v0.1",
        "executorVersion": "1.0.0",
        "supportsCancel": True,
        "supportsIdempotency": True,
        "supportsRecoveryQuery": True,
        "observabilityLevel": "structured",
        "permissionLevel": "enforced",
    },
}


@dataclass(frozen=True)
class ExecutionPlan:
    plan_version: str
    package_digest: str
    binding_digest: str | None
    workflow_id: str
    defaults: dict[str, int]
    input_schema_digest: str
    output_schema_digest: str
    nodes: dict[str, dict[str, Any]]
    edges: list[dict[str, str]]
    source_map: dict[str, dict[str, str]]
    required_features: list[str]
    compiled_plan_digest: str

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "planVersion": self.plan_version,
            "packageDigest": self.package_digest,
            "bindingDigest": self.binding_digest,
            "workflowId": self.workflow_id,
            "defaults": self.defaults,
            "inputSchemaDigest": self.input_schema_digest,
            "outputSchemaDigest": self.output_schema_digest,
            "nodes": self.nodes,
            "edges": self.edges,
            "sourceMap": self.source_map,
            "requiredFeatures": self.required_features,
        }
        if include_digest:
            result["compiledPlanDigest"] = self.compiled_plan_digest
        return result


@dataclass(frozen=True)
class CompileResult:
    plans: dict[str, ExecutionPlan]
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        return not self.diagnostics


def compile_package(
    package_dir: Path,
    *,
    binding_path: Path | None = None,
    omit_slots: set[str] | None = None,
    feature_set: set[str] | None = None,
) -> CompileResult:
    root = package_dir.resolve()
    if not root.is_dir():
        return CompileResult({}, [_diagnostic("PACKAGE_NOT_FOUND", root, "包目录不存在。")])

    try:
        package_document = load_document(root / "manifest.yaml")
    except DiagnosticError as exc:
        return CompileResult({}, [exc.diagnostic])
    try:
        package = WorkflowPackage.model_validate(package_document.value)
    except ValidationError as exc:
        return CompileResult({}, [_model_diagnostic(exc, root / "manifest.yaml")])

    diagnostics = _validate_package_references(package, root / "manifest.yaml")
    if diagnostics:
        return CompileResult({}, diagnostics)
    diagnostics = _validate_features(package, root / "manifest.yaml", feature_set)
    if diagnostics:
        return CompileResult({}, diagnostics)
    diagnostics = _scan_for_secret_material(root)
    if diagnostics:
        return CompileResult({}, diagnostics)

    workflows: dict[str, tuple[Path, Workflow]] = {}
    for workflow_id, relative_path in package.spec.workflows.items():
        workflow_path, path_diagnostic = _resolve_package_path(root, relative_path)
        if path_diagnostic is not None:
            return CompileResult({}, [path_diagnostic])
        if workflow_path is None:
            return CompileResult(
                {},
                [
                    _diagnostic(
                        "FILE_NOT_FOUND",
                        root / "manifest.yaml",
                        "Workflow 资源路径无法解析。",
                    )
                ],
            )
        try:
            workflow_document = load_document(workflow_path)
            workflow = Workflow.model_validate(workflow_document.value)
        except DiagnosticError as exc:
            return CompileResult({}, [exc.diagnostic])
        except ValidationError as exc:
            return CompileResult({}, [_model_diagnostic(exc, workflow_path)])
        workflows[workflow_id] = (workflow_path, workflow)

    nested_diagnostic = _validate_nested_workflows(package, workflows)
    if nested_diagnostic is not None:
        return CompileResult({}, [nested_diagnostic])
    resource_diagnostics = _validate_package_resources(package, root)
    if resource_diagnostics:
        return CompileResult({}, resource_diagnostics)
    lock_diagnostics = _validate_package_lock(root)
    if lock_diagnostics:
        return CompileResult({}, lock_diagnostics)

    workflow_output_schemas: dict[str, Path] = {}
    for workflow_id, (workflow_path, workflow) in workflows.items():
        schema_path, path_diagnostic = _resolve_package_path(root, workflow.spec.output_schema)
        if path_diagnostic is not None:
            return CompileResult({}, [path_diagnostic])
        if schema_path is None:
            return CompileResult(
                {},
                [_diagnostic("FILE_NOT_FOUND", workflow_path, "Workflow 输出 Schema 无法解析。")],
            )
        workflow_output_schemas[workflow_id] = schema_path

    package_hash = package_digest(root)
    binding_model: BindingSet | None = None
    binding_hash: str | None = None
    if binding_path is not None:
        try:
            binding_document = load_document(binding_path.resolve())
            binding_model = BindingSet.model_validate(binding_document.value)
        except DiagnosticError as exc:
            return CompileResult({}, [exc.diagnostic])
        except ValidationError as exc:
            return CompileResult({}, [_model_diagnostic(exc, binding_path)])
        binding_value = binding_model.model_dump(mode="json", by_alias=True, exclude_none=True)
        binding_hash = binding_digest(binding_value)

    plans: dict[str, ExecutionPlan] = {}
    binding_file = str(binding_path.resolve()) if binding_path is not None else None
    for workflow_id, (workflow_path, workflow) in workflows.items():
        workflow_result = _compile_workflow(
            root,
            package,
            workflow_id,
            workflow_path,
            workflow,
            binding_model,
            omit_slots or set(),
            package_hash,
            binding_hash,
            binding_file,
            workflow_output_schemas,
        )
        if isinstance(workflow_result, Diagnostic):
            return CompileResult({}, [workflow_result])
        plan, workflow_diagnostics = workflow_result
        if workflow_diagnostics:
            return CompileResult({}, workflow_diagnostics)
        if plan is not None:
            plans[workflow_id] = plan
    return CompileResult(plans, [])


def _compile_workflow(
    root: Path,
    package: WorkflowPackage,
    workflow_id: str,
    workflow_path: Path,
    workflow: Workflow,
    binding: BindingSet | None,
    omit_slots: set[str],
    package_hash: str,
    binding_hash: str | None,
    binding_file: str | None,
    workflow_output_schemas: dict[str, Path],
) -> tuple[ExecutionPlan | None, list[Diagnostic]] | Diagnostic:
    file = str(workflow_path)
    diagnostics = validate_graph(workflow.spec.nodes, workflow.spec.entry, file)
    if diagnostics:
        return None, diagnostics

    workflow_input_schema, input_path_diagnostic = _resolve_package_path(
        root, workflow.spec.input_schema
    )
    if input_path_diagnostic is not None:
        return None, [input_path_diagnostic]
    if workflow_input_schema is None:
        return None, [
            _diagnostic(
                "FILE_NOT_FOUND",
                workflow_path,
                "Workflow 输入 Schema 无法解析。",
            )
        ]

    for relative_schema, pointer in (
        (workflow.spec.input_schema, "/spec/inputSchema"),
        (workflow.spec.output_schema, "/spec/outputSchema"),
    ):
        _, schema_diagnostic = _validate_schema_resource(root, relative_schema, pointer)
        if schema_diagnostic is not None:
            return None, [schema_diagnostic]

    node_output_schemas: dict[str, SchemaSource] = {}
    for node_id, node in workflow.spec.nodes.items():
        if isinstance(node, CallNode):
            for schema_name, relative_schema in (
                ("inputSchema", node.input_schema),
                ("outputSchema", node.output_schema),
            ):
                schema_path, schema_diagnostic = _validate_schema_resource(
                    root,
                    relative_schema,
                    f"/spec/nodes/{_escape(node_id)}/{schema_name}",
                )
                if schema_diagnostic is not None:
                    return None, [schema_diagnostic]
                if schema_name == "outputSchema" and schema_path is not None:
                    node_output_schemas[node_id] = schema_path
        elif isinstance(node, (WorkflowNode, RepeatNode)):
            child_schema = workflow_output_schemas.get(node.workflow)
            if child_schema is not None:
                node_output_schemas[node_id] = child_schema
        elif isinstance(node, ParallelNode):
            node_output_schemas[node_id] = _parallel_output_schema(node, workflow_output_schemas)

    diagnostics = _validate_workflow_references(
        root,
        workflow_path,
        workflow,
        set(package.spec.workflows),
        node_output_schemas,
        workflow_input_schema,
        _error_output_sources(workflow),
        root,
    )
    if diagnostics:
        return None, diagnostics
    diagnostics = _validate_binding(workflow, binding, omit_slots, binding_file or file)
    if diagnostics:
        return None, diagnostics

    nodes: dict[str, dict[str, Any]] = {}
    source_map: dict[str, dict[str, str]] = {}
    for node_id, node in workflow.spec.nodes.items():
        dumped = _dump_model(node)
        retry: dict[str, Any] = {}
        deadline = workflow.spec.defaults.call_deadline_seconds
        if isinstance(node, CallNode):
            retry = _dump_model(node.retry)
            if not {"max_attempts", "maxAttempts"} & node.retry.model_fields_set:
                retry["maxAttempts"] = workflow.spec.defaults.max_attempts
            deadline = node.deadline_seconds or workflow.spec.defaults.call_deadline_seconds
        elif node.deadline_seconds is not None:
            deadline = node.deadline_seconds
        nodes[node_id] = {
            "id": node_id,
            "type": node.type,
            "definition": dumped,
            "defaults": {"deadlineSeconds": deadline, "retry": retry},
        }
        if isinstance(node, ParallelNode):
            nodes[node_id]["defaults"]["maxConcurrency"] = (
                node.max_concurrency or workflow.spec.defaults.max_concurrency
            )
        source_map[node_id] = {
            "file": file,
            "pointer": f"/spec/nodes/{_escape(node_id)}",
        }

    edges = [
        {"from": source, "to": target}
        for source, node in workflow.spec.nodes.items()
        for target in _targets(node)
    ]
    input_schema = _resolve_required_schema(root, workflow.spec.input_schema)
    output_schema = _resolve_required_schema(root, workflow.spec.output_schema)
    if input_schema is None or output_schema is None:
        return None, [
            _diagnostic(
                "FILE_NOT_FOUND",
                root / "manifest.yaml",
                "Workflow Schema 路径无法解析。",
            )
        ]
    base_plan: dict[str, Any] = {
        "planVersion": "multiverse/v0.1",
        "packageDigest": package_hash,
        "bindingDigest": binding_hash,
        "workflowId": workflow_id,
        "defaults": _dump_model(workflow.spec.defaults),
        "inputSchemaDigest": sha256_digest(input_schema.read_bytes()),
        "outputSchemaDigest": sha256_digest(output_schema.read_bytes()),
        "nodes": nodes,
        "edges": edges,
        "sourceMap": source_map,
        "requiredFeatures": sorted(package.spec.required_features),
    }
    digest = sha256_digest(canonical_json(base_plan))
    return (
        ExecutionPlan(
            plan_version="multiverse/v0.1",
            package_digest=package_hash,
            binding_digest=binding_hash,
            workflow_id=workflow_id,
            defaults=_dump_model(workflow.spec.defaults),
            input_schema_digest=base_plan["inputSchemaDigest"],
            output_schema_digest=base_plan["outputSchemaDigest"],
            nodes=nodes,
            edges=edges,
            source_map=source_map,
            required_features=sorted(package.spec.required_features),
            compiled_plan_digest=digest,
        ),
        [],
    )


def _validate_workflow_references(
    root: Path,
    workflow_path: Path,
    workflow: Workflow,
    workflow_ids: set[str],
    node_output_schemas: dict[str, SchemaSource],
    input_schema: Path,
    error_output_sources: dict[str, set[str]],
    package_root: Path,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    completed_nodes = _definitely_prior_nodes(workflow)
    for node_id, node in workflow.spec.nodes.items():
        pointer = f"/spec/nodes/{_escape(node_id)}"
        if isinstance(node, (CallNode,)):
            diagnostics.extend(
                validate_value_expr_references(
                    node.input,
                    allowed_nodes=set(workflow.spec.nodes),
                    completed_nodes=completed_nodes.get(node_id, set()),
                    file=str(workflow_path),
                    pointer=f"{pointer}/input",
                    node_output_schemas=node_output_schemas,
                    input_schema=input_schema,
                    package_root=package_root,
                    error_output_nodes=error_output_sources.get(node_id, set()),
                )
            )
        elif isinstance(node, (WorkflowNode, RepeatNode)):
            diagnostics.extend(
                validate_value_expr_references(
                    node.input,
                    allowed_nodes=set(workflow.spec.nodes),
                    completed_nodes=completed_nodes.get(node_id, set()),
                    file=str(workflow_path),
                    pointer=f"{pointer}/input",
                    allow_iteration=False,
                    node_output_schemas=node_output_schemas,
                    input_schema=input_schema,
                    package_root=package_root,
                    error_output_nodes=error_output_sources.get(node_id, set()),
                )
            )
            if node.workflow not in workflow_ids:
                diagnostics.append(
                    Diagnostic(
                        code="WORKFLOW_REFERENCE_MISSING",
                        file=str(workflow_path),
                        pointer=f"{pointer}/workflow",
                        message=f"嵌套 Workflow 不存在：{node.workflow}。",
                        suggestion="引用 manifest.spec.workflows 中声明的 workflow_id。",
                    )
                )
        elif isinstance(node, ParallelNode):
            for branch_id, branch in node.branches.items():
                diagnostics.extend(
                    validate_value_expr_references(
                        branch.input,
                        allowed_nodes=set(workflow.spec.nodes),
                        completed_nodes=completed_nodes.get(node_id, set()),
                        file=str(workflow_path),
                        pointer=f"{pointer}/branches/{_escape(branch_id)}/input",
                        node_output_schemas=node_output_schemas,
                        input_schema=input_schema,
                        package_root=package_root,
                        error_output_nodes=error_output_sources.get(node_id, set()),
                    )
                )
                if branch.workflow not in workflow_ids:
                    diagnostics.append(
                        Diagnostic(
                            code="WORKFLOW_REFERENCE_MISSING",
                            file=str(workflow_path),
                            pointer=f"{pointer}/branches/{_escape(branch_id)}/workflow",
                            message=f"嵌套 Workflow 不存在：{branch.workflow}。",
                            suggestion="引用 manifest.spec.workflows 中声明的 workflow_id。",
                        )
                    )
        if node.type == "switch":
            for index, case in enumerate(node.cases):
                diagnostics.extend(
                    validate_predicate_references(
                        case.when,
                        allowed_nodes=set(workflow.spec.nodes),
                        completed_nodes=completed_nodes.get(node_id, set()),
                        file=str(workflow_path),
                        pointer=f"{pointer}/cases/{index}/when",
                        node_output_schemas=node_output_schemas,
                        input_schema=input_schema,
                        package_root=package_root,
                        error_output_nodes=error_output_sources.get(node_id, set()),
                    )
                )
        if isinstance(node, EndNode) and node.output is not None:
            diagnostics.extend(
                validate_value_expr_references(
                    node.output,
                    allowed_nodes=set(workflow.spec.nodes),
                    completed_nodes=completed_nodes.get(node_id, set()),
                    file=str(workflow_path),
                    pointer=f"{pointer}/output",
                    node_output_schemas=node_output_schemas,
                    input_schema=input_schema,
                    package_root=package_root,
                    error_output_nodes=error_output_sources.get(node_id, set()),
                )
            )
        if node.type == "repeat":
            diagnostics.extend(
                validate_predicate_references(
                    node.until,
                    allowed_nodes=set(workflow.spec.nodes),
                    completed_nodes=completed_nodes.get(node_id, set()),
                    file=str(workflow_path),
                    pointer=f"{pointer}/until",
                    allow_iteration=True,
                    node_output_schemas=node_output_schemas,
                    input_schema=input_schema,
                    package_root=package_root,
                    error_output_nodes=error_output_sources.get(node_id, set()),
                )
            )
            diagnostics.extend(
                validate_value_expr_references(
                    node.feedback,
                    allowed_nodes=set(workflow.spec.nodes),
                    completed_nodes=completed_nodes.get(node_id, set()),
                    file=str(workflow_path),
                    pointer=f"{pointer}/feedback",
                    allow_iteration=True,
                    node_output_schemas=node_output_schemas,
                    input_schema=input_schema,
                    package_root=package_root,
                    error_output_nodes=error_output_sources.get(node_id, set()),
                )
            )
    return diagnostics


def _validate_binding(
    workflow: Workflow,
    binding: BindingSet | None,
    omit_slots: set[str],
    file: str,
) -> list[Diagnostic]:
    if binding is None:
        return []
    slots = set(binding.spec.slots) - omit_slots
    diagnostics: list[Diagnostic] = []
    for node_id, node in workflow.spec.nodes.items():
        if not isinstance(node, CallNode):
            continue
        if node.slot not in slots:
            diagnostics.append(
                Diagnostic(
                    code="BINDING_UNRESOLVED",
                    file=file,
                    pointer=f"/spec/slots/{_escape(node.slot)}",
                    message=f"逻辑 slot 未绑定：{node.slot}。",
                    suggestion="为该 slot 配置一个受信任的执行器。",
                )
            )
            continue
        slot = binding.spec.slots[node.slot]
        descriptor = _EXECUTOR_DESCRIPTORS.get(slot.executor_ref)
        if descriptor is None:
            diagnostics.append(
                Diagnostic(
                    code="EXECUTOR_UNRESOLVED",
                    file=file,
                    pointer=f"/spec/slots/{_escape(node.slot)}/executorRef",
                    message=f"执行器未注册：{slot.executor_ref}。",
                    suggestion="使用环境已注册且受信任的 executorRef。",
                )
            )
            continue
        if slot.adapter != descriptor["adapter"]:
            diagnostics.append(
                Diagnostic(
                    code="EXECUTOR_ADAPTER_MISMATCH",
                    file=file,
                    pointer=f"/spec/slots/{_escape(node.slot)}/adapter",
                    message=(
                        f"执行器 {slot.executor_ref} 要求 adapter "
                        f"{descriptor['adapter']}，实际为 {slot.adapter}。"
                    ),
                    suggestion="使用 ExecutorDescriptor 声明的 adapter。",
                )
            )
            continue
        capabilities = descriptor["capabilities"]
        for capability in node.requires.capabilities:
            if capability not in capabilities:
                diagnostics.append(
                    Diagnostic(
                        code="CAPABILITY_MISMATCH",
                        file=file,
                        pointer=f"/spec/nodes/{_escape(node_id)}/requires/capabilities",
                        message=f"执行器 {slot.executor_ref} 不声明能力 {capability}。",
                    )
                )
    return diagnostics


def _validate_package_resources(
    package: WorkflowPackage,
    root: Path,
) -> list[Diagnostic]:
    for index, relative_path in enumerate(package.spec.eval_suites):
        _, diagnostic = _resolve_package_path(root, relative_path)
        if diagnostic is not None:
            diagnostic = Diagnostic(
                code=diagnostic.code,
                file=diagnostic.file,
                pointer=f"/spec/evalSuites/{index}",
                message=diagnostic.message,
                severity=diagnostic.severity,
                suggestion=diagnostic.suggestion,
                details=diagnostic.details,
            )
            return [diagnostic]
    for asset_id, asset in package.spec.assets.items():
        _, diagnostic = _resolve_package_path(root, asset.path)
        if diagnostic is not None:
            diagnostic = Diagnostic(
                code=diagnostic.code,
                file=diagnostic.file,
                pointer=f"/spec/assets/{_escape(asset_id)}/path",
                message=diagnostic.message,
                severity=diagnostic.severity,
                suggestion=diagnostic.suggestion,
                details=diagnostic.details,
            )
            return [diagnostic]
    return []


def _validate_package_lock(root: Path) -> list[Diagnostic]:
    lock_path = root / "package.lock.json"
    if not lock_path.is_file():
        return []
    try:
        document = load_document(lock_path)
    except DiagnosticError as exc:
        return [exc.diagnostic]
    value = document.value
    if not isinstance(value, dict):
        return [
            _diagnostic(
                "PACKAGE_LOCK_INVALID",
                lock_path,
                "package.lock.json 根值必须是对象。",
            )
        ]
    files = value.get("files")
    digest = value.get("packageDigest")
    if not isinstance(files, list) or not isinstance(digest, str):
        return [
            _diagnostic(
                "PACKAGE_LOCK_INVALID",
                lock_path,
                "package.lock.json 必须包含 files 数组和 packageDigest。",
            )
        ]
    actual_files = package_file_manifest(root)
    if files != actual_files:
        return [
            _diagnostic(
                "PACKAGE_LOCK_MISMATCH",
                lock_path,
                "package.lock.json 的文件清单与包实际文件不一致。",
            )
        ]
    if digest != package_digest(root):
        return [
            _diagnostic(
                "PACKAGE_LOCK_MISMATCH",
                lock_path,
                "package.lock.json 的 packageDigest 与包实际摘要不一致。",
            )
        ]
    return []


def _parallel_output_schema(
    node: ParallelNode,
    workflow_output_schemas: dict[str, Path],
) -> dict[str, Any]:
    branches: dict[str, Any] = {}
    for branch_id, branch in node.branches.items():
        schema_path = workflow_output_schemas.get(branch.workflow)
        if schema_path is None:
            branches[branch_id] = {}
            continue
        try:
            document = load_document(schema_path)
            branches[branch_id] = document.value if isinstance(document.value, dict) else {}
        except DiagnosticError:
            branches[branch_id] = {}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["branches"],
        "properties": {
            "branches": {
                "type": "object",
                "required": sorted(branches),
                "properties": branches,
                "additionalProperties": False,
            }
        },
        "additionalProperties": False,
    }


def _error_output_sources(workflow: Workflow) -> dict[str, set[str]]:
    adjacency = {node_id: _targets(node) for node_id, node in workflow.spec.nodes.items()}
    result: dict[str, set[str]] = {node_id: set() for node_id in workflow.spec.nodes}
    for source, node in workflow.spec.nodes.items():
        if node.on_error is None:
            continue
        for consumer in _reachable_nodes(adjacency, node.on_error):
            result[consumer].add(source)
    return result


def _reachable_nodes(adjacency: dict[str, list[str]], entry: str) -> set[str]:
    reachable: set[str] = set()
    stack = [entry]
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        stack.extend(adjacency.get(node_id, []))
    return reachable


def _validate_nested_workflows(
    package: WorkflowPackage,
    workflows: dict[str, tuple[Path, Workflow]],
) -> Diagnostic | None:
    references: dict[str, set[str]] = {workflow_id: set() for workflow_id in workflows}
    for workflow_id, (workflow_path, workflow) in workflows.items():
        for node in workflow.spec.nodes.values():
            if isinstance(node, (WorkflowNode, RepeatNode)):
                references[workflow_id].add(node.workflow)
            elif isinstance(node, ParallelNode):
                references[workflow_id].update(branch.workflow for branch in node.branches.values())
        missing = references[workflow_id] - set(workflows)
        if missing:
            missing_workflow = sorted(missing)[0]
            return Diagnostic(
                code="WORKFLOW_REFERENCE_MISSING",
                file=str(workflow_path),
                pointer="/spec/nodes",
                message=f"嵌套 Workflow 不存在：{missing_workflow}。",
                suggestion="引用 manifest.spec.workflows 中声明的 workflow_id。",
            )

    visiting: list[str] = []
    memo: dict[str, int] = {}

    def visit(workflow_id: str) -> int:
        if workflow_id in visiting:
            start = visiting.index(workflow_id)
            cycle = visiting[start:] + [workflow_id]
            path = workflows[workflow_id][0]
            raise _NestedWorkflowError(
                Diagnostic(
                    code="NESTED_WORKFLOW_CYCLE",
                    file=str(path),
                    pointer="/spec/nodes",
                    message=f"嵌套 Workflow 存在递归：{' -> '.join(cycle)}。",
                    suggestion="移除直接或间接递归引用。",
                )
            )
        if workflow_id in memo:
            return memo[workflow_id]
        visiting.append(workflow_id)
        child_depths = [visit(child) for child in sorted(references[workflow_id])]
        visiting.pop()
        depth = 1 + max(child_depths, default=0)
        memo[workflow_id] = depth
        return depth

    try:
        for workflow_id in package.spec.workflows:
            depth = visit(workflow_id)
            if depth > 8:
                path = workflows[workflow_id][0]
                return Diagnostic(
                    code="NESTED_WORKFLOW_DEPTH",
                    file=str(path),
                    pointer="/spec/nodes",
                    message="嵌套 Workflow 深度不能超过 8。",
                    suggestion="减少嵌套层级或拆分工作流包。",
                )
    except _NestedWorkflowError as exc:
        return exc.diagnostic
    return None


class _NestedWorkflowError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic


def _validate_features(
    package: WorkflowPackage,
    path: Path,
    feature_set: set[str] | None,
) -> list[Diagnostic]:
    supported = feature_set if feature_set is not None else _SUPPORTED_FEATURES
    for index, feature in enumerate(package.spec.required_features):
        if feature not in supported:
            return [
                Diagnostic(
                    code="UNSUPPORTED_FEATURE",
                    file=str(path),
                    pointer=f"/spec/requiredFeatures/{index}",
                    message=f"未实现必需功能：{feature}。",
                )
            ]
    return []


def _validate_package_references(package: WorkflowPackage, path: Path) -> list[Diagnostic]:
    declared = set(package.spec.workflows)
    for index, workflow_id in enumerate(package.spec.entrypoints):
        if workflow_id not in declared:
            return [
                Diagnostic(
                    code="WORKFLOW_REFERENCE_MISSING",
                    file=str(path),
                    pointer=f"/spec/entrypoints/{index}",
                    message=f"入口 Workflow 不存在：{workflow_id}。",
                    suggestion="将 entrypoints 指向 spec.workflows 中声明的 workflow_id。",
                )
            ]
    return []


def _validate_schema_resource(
    root: Path,
    relative_path: str,
    pointer: str,
) -> tuple[Path | None, Diagnostic | None]:
    if Path(relative_path).suffix.lower() != ".json":
        return None, Diagnostic(
            code="SCHEMA_PATH_INVALID",
            file=str(root / "manifest.yaml"),
            pointer=pointer,
            message=f"Schema 资源必须使用 .json 文件：{relative_path}。",
            suggestion="将 Schema 保存为 Draft 2020-12 JSON 文件。",
        )
    schema_path, path_diagnostic = _resolve_package_path(root, relative_path)
    if path_diagnostic is not None:
        return None, path_diagnostic
    if schema_path is None:
        return None, _diagnostic("FILE_NOT_FOUND", root / "manifest.yaml", "Schema 路径无法解析。")
    schema, schema_diagnostic = validate_schema_file(schema_path, root)
    if schema_diagnostic is not None:
        return None, schema_diagnostic
    if schema is None:
        return None, Diagnostic(
            code="SCHEMA_FILE_INVALID",
            file=str(schema_path),
            pointer=pointer,
            message="Schema 文件没有返回对象。",
        )
    try:
        schema_validator(schema, schema_path, root).check_schema(schema)
    except Exception as exc:
        return None, Diagnostic(
            code="SCHEMA_FILE_INVALID",
            file=str(schema_path),
            pointer=pointer,
            message=f"Schema 校验失败：{exc}。",
        )
    return schema_path, None


def _scan_for_secret_material(root: Path) -> list[Diagnostic]:
    forbidden_names = {".env", "credentials.json", "secrets.json", "private.key", "private.pem"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.name.lower() in forbidden_names or path.suffix.lower() in {".pem", ".key"}:
            return [
                Diagnostic(
                    code="PACKAGE_SECRET_MATERIAL",
                    file=str(path),
                    pointer="",
                    message=f"包中禁止包含疑似凭据文件：{relative}。",
                    suggestion="使用 secretRefs 引用环境机密，不要把机密内容放入包。",
                )
            ]
    return []


def _resolve_package_path(root: Path, relative_path: str) -> tuple[Path | None, Diagnostic | None]:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return None, Diagnostic(
            code="INVALID_PATH",
            file=str(root / "manifest.yaml"),
            pointer="",
            message=f"资源路径必须是包根下的相对路径：{relative_path}。",
        )
    candidate = (root / path).resolve()
    if root not in candidate.parents and candidate != root:
        return None, Diagnostic(
            code="INVALID_PATH",
            file=str(root / "manifest.yaml"),
            pointer="",
            message=f"资源路径越过包根：{relative_path}。",
        )
    if not candidate.is_file():
        return None, Diagnostic(
            code="FILE_NOT_FOUND",
            file=str(root / "manifest.yaml"),
            pointer="",
            message=f"包内资源不存在：{relative_path}。",
        )
    return candidate, None


def _resolve_required_schema(root: Path, relative_path: str) -> Path | None:
    candidate = (root / relative_path).resolve()
    return candidate if candidate.is_file() else None


def _definitely_prior_nodes(workflow: Workflow) -> dict[str, set[str]]:
    edges = {node_id: _targets(node) for node_id, node in workflow.spec.nodes.items()}
    predecessors: dict[str, set[str]] = {node_id: set() for node_id in workflow.spec.nodes}
    for source, targets in edges.items():
        for target in targets:
            if target in predecessors:
                predecessors[target].add(source)
    node_ids = set(workflow.spec.nodes)
    dominators = {node_id: set(node_ids) for node_id in node_ids}
    dominators[workflow.spec.entry] = {workflow.spec.entry}
    changed = True
    while changed:
        changed = False
        for node_id in node_ids - {workflow.spec.entry}:
            prior_nodes = predecessors[node_id]
            if not prior_nodes:
                updated = {node_id}
            else:
                common = set.intersection(*(dominators[node] for node in prior_nodes))
                updated = common | {node_id}
            if updated != dominators[node_id]:
                dominators[node_id] = updated
                changed = True
    return {node_id: dominators[node_id] - {node_id} for node_id in workflow.spec.nodes}


def _targets(node: Any) -> list[str]:
    targets: list[str] = []
    if node.type in {"call", "workflow", "parallel", "repeat"}:
        targets.append(node.next)
    elif node.type == "switch":
        targets.extend(case.next for case in node.cases)
        targets.append(node.default)
    if node.on_error is not None:
        targets.append(node.on_error)
    return targets


def _dump_model(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def _model_diagnostic(exc: ValidationError, path: Path) -> Diagnostic:
    error = exc.errors()[0]
    location = "/" + "/".join(_escape(str(part)) for part in error.get("loc", ()))
    return Diagnostic(
        code="INVALID_SPEC",
        file=str(path),
        pointer=location if location != "/" else "",
        message=str(error.get("msg", "协议资源无效。")),
        details={"type": error.get("type")},
    )


def _diagnostic(code: str, path: Path, message: str) -> Diagnostic:
    return Diagnostic(code=code, file=str(path), pointer="", message=message)


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")

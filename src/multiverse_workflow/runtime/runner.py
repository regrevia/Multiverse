from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import ValidationError as JsonSchemaValidationError

from multiverse_workflow.compiler import ExecutionPlan, compile_package
from multiverse_workflow.compiler.references import schema_validator, validate_schema_file
from multiverse_workflow.protocol.loader import load_document
from multiverse_workflow.protocol.models import BindingSet, Workflow, WorkflowPackage
from multiverse_workflow.runtime.executors import ExecutorError, execute_builtin
from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry


class RunError(RuntimeError):
    """A run cannot continue because its input or execution result is invalid."""


class Runner:
    def __init__(
        self,
        package_dir: Path,
        *,
        binding_path: Path,
        database_path: Path,
        namespace: str = "local",
        executor_registry: ExecutorRegistry | None = None,
    ) -> None:
        self.package_dir = package_dir.resolve()
        self.namespace = namespace
        result = compile_package(self.package_dir, binding_path=binding_path)
        if not result.ok:
            detail = "; ".join(diagnostic.code for diagnostic in result.diagnostics)
            raise RunError(f"package compilation failed: {detail}")
        self._plans = result.plans
        self._binding = BindingSet.model_validate(load_document(binding_path.resolve()).value)
        package = WorkflowPackage.model_validate(
            load_document(self.package_dir / "manifest.yaml").value
        )
        self._workflows: dict[str, Workflow] = {}
        for workflow_id, relative_path in package.spec.workflows.items():
            self._workflows[workflow_id] = Workflow.model_validate(
                load_document(self.package_dir / relative_path).value
            )
        self._executor_registry = (
            executor_registry or local_executor_registry()
        ).snapshot()
        self.ledger = Ledger(database_path)

    def start(self, input_value: Any, workflow_id: str | None = None) -> dict[str, Any]:
        workflow_id = workflow_id or next(iter(self._plans))
        plan = self._plan(workflow_id)
        workflow = self._workflows[workflow_id]
        self._validate_schema(input_value, workflow.spec.input_schema)
        self._preflight_execution(plan)
        deadline = datetime.now(UTC) + timedelta(
            seconds=plan.defaults["runDeadlineSeconds"]
        )
        run = self.ledger.create_run(
            namespace=self.namespace,
            workflow_id=workflow_id,
            package_digest=plan.package_digest,
            binding_digest=plan.binding_digest,
            plan=plan.as_dict(),
            input_value=input_value,
            deadline_at=_timestamp(deadline),
        )
        scope = self.ledger.create_scope(run["id"], workflow_id, path=["root"])
        self.ledger.update_run(
            run["id"],
            status="running",
            current_node_id=workflow.spec.entry,
        )
        return self._drive(run["id"], scope["id"], workflow.spec.entry)

    def pending_human_requests(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_human_requests(run_id=run_id, status="pending")

    def inspect(self, run_id: str) -> dict[str, Any] | None:
        return self.ledger.get_run(run_id)

    def decide(
        self,
        request_id: str,
        *,
        choice: str | None = None,
        decision: Any | None = None,
        comment: str,
        actor: str,
        subject_digest: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        request = self.ledger.get_human_request(request_id)
        if request is None:
            raise KeyError(f"human request not found: {request_id}")
        if idempotency_key is not None:
            previous = self.ledger.get_human_decision_by_idempotency_key(idempotency_key)
            if previous is not None:
                if previous["request_id"] != request_id:
                    raise LedgerConflict("idempotency key belongs to another request")
                run = self.ledger.get_run(request["run_id"])
                if run is None:
                    raise RunError("human request run is missing")
                return run
        request_type = request["request_type"]
        invocation = self.ledger.get_invocation(request["invocation_id"])
        if invocation is None:
            raise RunError("human request invocation is missing")
        run = self.ledger.get_run(request["run_id"])
        if run is None:
            raise RunError("human request run is missing")
        plan = self._plan(run["workflow_id"])
        self._require_matching_definition(run, plan)
        node = plan.nodes[invocation["node_id"]]
        if request_type in {"approval", "review"}:
            if choice is None and isinstance(decision, dict):
                raw_choice = decision.get("decision")
                if isinstance(raw_choice, str):
                    choice = raw_choice
                    if comment == "" and isinstance(decision.get("comment"), str):
                        comment = decision["comment"]
            if choice is None:
                raise LedgerConflict("review request requires --choice")
            output = {"decision": choice, "comment": comment}
        else:
            if decision is None:
                raise LedgerConflict("input request requires a structured decision")
            output = decision
        self._validate_schema(output, node["definition"]["outputSchema"])
        self._validate_artifact_refs(request["run_id"], output)
        binding = self._binding.spec.slots[node["definition"]["slot"]]
        required_comment_choices = binding.config.get("requireCommentFor", [])
        if (
            request_type in {"approval", "review"}
            and isinstance(required_comment_choices, list)
            and choice in required_comment_choices
            and not comment.strip()
        ):
            raise LedgerConflict("comment is required for this decision")
        self.ledger.decide_human_request(
            request_id,
            choice=choice,
            decision=decision,
            comment=comment,
            expected_version=expected_version,
            subject_digest=subject_digest,
            actor=actor,
            idempotency_key=idempotency_key or f"decision-{uuid.uuid4().hex}",
        )
        attempt = self.ledger.latest_attempt(invocation["id"])
        decision = self.ledger.get_human_decision(request_id)
        if attempt is None or decision is None:
            raise RunError("human decision ledger records are incomplete")
        if request_type in {"approval", "review"}:
            output = {"decision": decision["choice"], "comment": decision["comment"]}
        else:
            output = json.loads(decision["decision_json"])
        self.ledger.finish_attempt(attempt["id"], status="succeeded", output=output)
        self.ledger.finish_invocation(invocation["id"], status="succeeded", output=output)
        next_node = node["definition"]["next"]
        self.ledger.update_run(
            request["run_id"],
            status="running",
            current_node_id=next_node,
        )
        return self._drive(request["run_id"], invocation["scope_id"], next_node)

    def _drive(self, run_id: str, scope_id: str, node_id: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        plan = self._plan(run["workflow_id"])
        input_value = json.loads(run["input_json"])
        while True:
            node = plan.nodes[node_id]
            definition = node["definition"]
            if node["type"] == "call":
                invocation = self.ledger.get_invocation_for_node(scope_id, node_id)
                if invocation is not None and invocation["status"] == "waiting":
                    return self.ledger.update_run(
                        run_id,
                        status="waiting",
                        current_node_id=node_id,
                    )
                if invocation is not None and invocation["status"] == "succeeded":
                    output = json.loads(invocation["output_json"])
                else:
                    output = self._execute_call(
                        run_id,
                        scope_id,
                        node_id,
                        definition,
                        input_value,
                        plan,
                    )
                    if output is None:
                        return self.ledger.get_run(run_id)  # type: ignore[return-value]
                node_outputs = self._outputs(run_id)
                node_outputs[node_id] = output
                node_id = definition["next"]
                self.ledger.update_run(run_id, status="running", current_node_id=node_id)
                continue

            if node["type"] == "switch":
                node_outputs = self._outputs(run_id)
                next_node = definition["default"]
                for case in definition["cases"]:
                    if self._predicate(case["when"], input_value, node_outputs):
                        next_node = case["next"]
                        self.ledger.record_event(
                            run_id,
                            "switch.selected",
                            {"nodeId": node_id, "caseId": case["id"], "next": next_node},
                            scope_id=scope_id,
                        )
                        break
                else:
                    self.ledger.record_event(
                        run_id,
                        "switch.selected",
                        {"nodeId": node_id, "caseId": "default", "next": next_node},
                        scope_id=scope_id,
                    )
                node_id = next_node
                self.ledger.update_run(run_id, status="running", current_node_id=node_id)
                continue

            if node["type"] == "end":
                if definition["outcome"] == "succeeded":
                    output = self._resolve_expr(
                        definition["output"], input_value, self._outputs(run_id)
                    )
                    workflow = self._workflows[run["workflow_id"]]
                    self._validate_schema(output, workflow.spec.output_schema)
                    return self.ledger.update_run(
                        run_id,
                        status="succeeded",
                        current_node_id=node_id,
                        output=output,
                    )
                error = definition["error"]
                return self.ledger.update_run(
                    run_id,
                    status="failed",
                    current_node_id=node_id,
                    error=error,
                )

            raise RunError(f"unsupported runtime node type: {node['type']}")

    def _execute_call(
        self,
        run_id: str,
        scope_id: str,
        node_id: str,
        definition: dict[str, Any],
        root_input: Any,
        plan: ExecutionPlan,
    ) -> Any | None:
        input_value = self._resolve_expr(definition["input"], root_input, self._outputs(run_id))
        self._validate_schema(input_value, definition["inputSchema"])
        invocation = self.ledger.create_invocation(
            run_id,
            scope_id,
            node_id,
            input_value,
        )
        attempt = self.ledger.create_attempt(
            invocation["id"],
            input_value=input_value,
            dispatch_key=f"{invocation['id']}:1",
            effect_key=invocation["id"],
        )
        binding = self._binding.spec.slots[definition["slot"]]
        if binding.adapter not in {"builtin", "human"}:
            error = {"code": "EXECUTOR_UNSUPPORTED", "message": "HTTP Job runtime is not enabled."}
            self.ledger.finish_attempt(attempt["id"], status="failed", error=error)
            self.ledger.finish_invocation(invocation["id"], status="failed", error=error)
            self.ledger.update_run(
                run_id,
                status="failed",
                current_node_id=node_id,
                error=error,
            )
            return None
        try:
            result = execute_builtin(binding.executor_ref, input_value, binding.config)
        except ExecutorError as exc:
            error = {"code": "EXECUTOR_FAILED", "message": str(exc)}
            self.ledger.finish_attempt(attempt["id"], status="failed", error=error)
            self.ledger.finish_invocation(invocation["id"], status="failed", error=error)
            self.ledger.update_run(
                run_id,
                status="failed",
                current_node_id=node_id,
                error=error,
            )
            return None
        if result.human_request is not None:
            request_spec = result.human_request
            subject_digest = _digest_json(input_value)
            self.ledger.create_human_request(
                run_id=run_id,
                scope_id=scope_id,
                invocation_id=invocation["id"],
                request_type=request_spec.request_type,
                title=request_spec.title,
                instructions=request_spec.instructions,
                input_value=input_value,
                subject_digest=subject_digest,
                choices=request_spec.choices,
                decision_schema=self._load_schema(definition["outputSchema"]),
                authorized_subjects=request_spec.authorized_subjects,
                expires_at=_timestamp(
                    datetime.now(UTC)
                    + timedelta(
                        seconds=plan.nodes[node_id]["defaults"]["deadlineSeconds"]
                    )
                ),
            )
            self.ledger.finish_attempt(attempt["id"], status="waiting")
            self.ledger.finish_invocation(invocation["id"], status="waiting")
            self.ledger.update_run(run_id, status="waiting", current_node_id=node_id)
            return None
        output = result.output
        self._validate_schema(output, definition["outputSchema"])
        self.ledger.finish_attempt(attempt["id"], status="succeeded", output=output)
        self.ledger.finish_invocation(invocation["id"], status="succeeded", output=output)
        return output

    def _load_schema(self, relative_path: str) -> dict[str, Any]:
        path = (self.package_dir / relative_path).resolve()
        schema, diagnostic = validate_schema_file(path, self.package_dir)
        if diagnostic is not None or schema is None:
            raise RunError(f"schema invalid: {relative_path}")
        return schema

    def _validate_artifact_refs(self, run_id: str, value: Any) -> None:
        refs: list[str] = []

        def visit(current: Any) -> None:
            if isinstance(current, dict):
                for key, child in current.items():
                    if key in {"artifact_refs", "artifactRefs"}:
                        if not isinstance(child, list) or not all(
                            isinstance(item, str) for item in child
                        ):
                            raise LedgerConflict("artifact_refs must be a string array")
                        refs.extend(child)
                    else:
                        visit(child)
            elif isinstance(current, list):
                for child in current:
                    visit(child)

        visit(value)
        self.ledger.validate_artifact_refs(run_id, refs)

    def _outputs(self, run_id: str) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for invocation in self.ledger.list_invocations(run_id):
            if invocation["status"] == "succeeded" and invocation["output_json"] is not None:
                outputs[invocation["node_id"]] = json.loads(invocation["output_json"])
        return outputs

    def _plan(self, workflow_id: str) -> ExecutionPlan:
        try:
            return self._plans[workflow_id]
        except KeyError as exc:
            raise RunError(f"workflow not found: {workflow_id}") from exc

    def _preflight_execution(self, plan: ExecutionPlan) -> None:
        issues = self._executor_registry.preflight(nodes=plan.nodes, binding=self._binding)
        if issues:
            detail = "; ".join(
                f"{issue.code} ({issue.node_id}): {issue.message}" for issue in issues
            )
            raise RunError(f"runtime preflight failed: {detail}")

    def _require_matching_definition(
        self,
        run: dict[str, Any],
        plan: ExecutionPlan,
    ) -> None:
        if run["package_digest"] != plan.package_digest:
            raise RunError("runtime definition drift: package digest changed")
        if run["binding_digest"] != plan.binding_digest:
            raise RunError("runtime definition drift: binding digest changed")

    def _validate_schema(self, value: Any, relative_path: str) -> None:
        path = (self.package_dir / relative_path).resolve()
        schema, diagnostic = validate_schema_file(path, self.package_dir)
        if diagnostic is not None or schema is None:
            raise RunError(f"schema invalid: {relative_path}")
        try:
            schema_validator(schema, path, self.package_dir).validate(value)
        except JsonSchemaValidationError as exc:
            raise RunError(f"schema validation failed: {relative_path}: {exc.message}") from exc

    def _resolve_expr(
        self,
        expression: dict[str, Any],
        root_input: Any,
        outputs: dict[str, Any],
    ) -> Any:
        if "literal" in expression:
            return expression["literal"]
        if "ref" in expression:
            reference = expression["ref"]
            root, _, fragment = reference.partition("#")
            if root == "input":
                value = root_input
            elif root.startswith("nodes.") and root.endswith(".output"):
                value = outputs[root[6:-7]]
            else:
                raise RunError(f"unsupported runtime reference: {reference}")
            return _pointer(value, fragment)
        if "object" in expression:
            return {
                key: self._resolve_expr(child, root_input, outputs)
                for key, child in expression["object"].items()
            }
        if "array" in expression:
            return [
                self._resolve_expr(child, root_input, outputs) for child in expression["array"]
            ]
        raise RunError("invalid ValueExpr in execution plan")

    def _predicate(
        self,
        predicate: dict[str, Any],
        root_input: Any,
        outputs: dict[str, Any],
    ) -> bool:
        if "all" in predicate:
            return all(self._predicate(item, root_input, outputs) for item in predicate["all"])
        if "any" in predicate:
            return any(self._predicate(item, root_input, outputs) for item in predicate["any"])
        if "not" in predicate:
            return not self._predicate(predicate["not"], root_input, outputs)
        left = self._resolve_expr(predicate["left"], root_input, outputs)
        right = self._resolve_expr(predicate["right"], root_input, outputs)
        op = predicate["op"]
        if op == "eq":
            return bool(left == right)
        if op == "ne":
            return bool(left != right)
        if op == "lt":
            return bool(left < right)
        if op == "lte":
            return bool(left <= right)
        if op == "gt":
            return bool(left > right)
        if op == "gte":
            return bool(left >= right)
        if op == "in":
            return bool(left in right)
        raise RunError(f"unsupported predicate operator: {op}")


def _pointer(value: Any, fragment: str) -> Any:
    if not fragment:
        return value
    if not fragment.startswith("/"):
        raise RunError(f"invalid JSON Pointer: #{fragment}")
    current = value
    for raw_token in fragment[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RunError(f"JSON Pointer not found: #{fragment}") from exc
    return current


def _digest_json(value: Any) -> str:
    return _sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _sha256(value: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

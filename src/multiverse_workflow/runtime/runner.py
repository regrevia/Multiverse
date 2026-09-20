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
        self._executor_registry = (
            executor_registry or local_executor_registry()
        ).snapshot()
        result = compile_package(
            self.package_dir,
            binding_path=binding_path,
            executor_registry=self._executor_registry,
        )
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
        self.ledger = Ledger(database_path)

    def start(
        self,
        input_value: Any,
        workflow_id: str | None = None,
        *,
        rerun_of: str | None = None,
        rerun_reason: str | None = None,
    ) -> dict[str, Any]:
        workflow_id = workflow_id or next(iter(self._plans))
        plan = self._plan(workflow_id)
        workflow = self._workflows[workflow_id]
        self._validate_schema(input_value, workflow.spec.input_schema)
        for candidate_plan in self._plans.values():
            self._preflight_execution(candidate_plan)
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
            rerun_of=rerun_of,
            rerun_reason=rerun_reason,
        )
        scope = self.ledger.create_scope(
            run["id"],
            workflow_id,
            path=["root"],
            input_value=input_value,
        )
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

    def pause(self, run_id: str, *, expected_version: int, reason: str) -> dict[str, Any]:
        return self.ledger.control_run(
            run_id,
            operation="pause",
            expected_version=expected_version,
            reason=reason,
        )

    def resume(self, run_id: str, *, expected_version: int, reason: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        self._require_matching_definition(run, self._plan(run["workflow_id"]))
        resumed = self.ledger.control_run(
            run_id,
            operation="resume",
            expected_version=expected_version,
            reason=reason,
        )
        node_id = resumed["current_node_id"]
        if node_id is None:
            return resumed
        return self._drive(run_id, self._active_scope_for_node(run_id, node_id)["id"], node_id)

    def cancel(self, run_id: str, *, expected_version: int, reason: str) -> dict[str, Any]:
        return self.ledger.control_run(
            run_id,
            operation="cancel",
            expected_version=expected_version,
            reason=reason,
        )

    def rerun(
        self,
        run_id: str,
        *,
        reason: str,
        input_value: Any | None = None,
    ) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        if run["status"] not in {"succeeded", "failed", "cancelled"}:
            raise LedgerConflict("only a terminal run can be rerun")
        self._require_matching_definition(run, self._plan(run["workflow_id"]))
        return self.start(
            json.loads(run["input_json"]) if input_value is None else input_value,
            workflow_id=run["workflow_id"],
            rerun_of=run_id,
            rerun_reason=reason,
        )

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
                return self._resume_decided_request(request)
        request_type = request["request_type"]
        invocation = self.ledger.get_invocation(request["invocation_id"])
        if invocation is None:
            raise RunError("human request invocation is missing")
        run = self.ledger.get_run(request["run_id"])
        if run is None:
            raise RunError("human request run is missing")
        root_plan = self._plan(run["workflow_id"])
        self._require_matching_definition(run, root_plan)
        scope = self.ledger.get_scope(invocation["scope_id"])
        if scope is None:
            raise RunError("human request scope is missing")
        plan = self._plan(scope["workflow_id"])
        request_input = json.loads(request["input_json"])
        if (
            self._artifact_subject_digest(run["id"], request_input)
            != request["subject_digest"]
        ):
            raise LedgerConflict("human request subject integrity check failed")
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
        return self._resume_decided_request(request)

    def _resume_decided_request(self, request: dict[str, Any]) -> dict[str, Any]:
        invocation = self.ledger.get_invocation(request["invocation_id"])
        run = self.ledger.get_run(request["run_id"])
        if invocation is None:
            raise RunError("human request invocation is missing")
        if run is None:
            raise RunError("human request run is missing")
        root_plan = self._plan(run["workflow_id"])
        self._require_matching_definition(run, root_plan)
        scope = self.ledger.get_scope(invocation["scope_id"])
        if scope is None:
            raise RunError("human request scope is missing")
        plan = self._plan(scope["workflow_id"])
        if invocation["status"] == "succeeded":
            return run
        if invocation["status"] != "waiting":
            raise RunError(f"human request invocation cannot resume: {invocation['status']}")
        attempt = self.ledger.latest_attempt(invocation["id"])
        decision = self.ledger.get_human_decision(request["id"])
        if attempt is None or decision is None:
            raise RunError("human decision ledger records are incomplete")
        if request["request_type"] in {"approval", "review"}:
            output = {"decision": decision["choice"], "comment": decision["comment"]}
        else:
            output = json.loads(decision["decision_json"])
        self.ledger.finish_attempt(attempt["id"], status="succeeded", output=output)
        self.ledger.finish_invocation(invocation["id"], status="succeeded", output=output)
        node = plan.nodes[invocation["node_id"]]
        next_node = node["definition"]["next"]
        if run["control_mode"] == "pause":
            self.ledger.update_run(
                run["id"],
                status="paused",
                control_mode="pause",
                current_node_id=next_node,
            )
            return self.ledger.get_run(run["id"])  # type: ignore[return-value]
        self.ledger.update_run(
            run["id"],
            status="running",
            current_node_id=next_node,
        )
        return self._drive(run["id"], invocation["scope_id"], next_node)

    def _drive(self, run_id: str, scope_id: str, node_id: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        scope = self.ledger.get_scope(scope_id)
        if scope is None:
            raise RunError("execution scope is missing")
        if run["control_mode"] != "run":
            return run
        plan = self._plan(scope["workflow_id"])
        input_json = scope["input_json"] or run["input_json"]
        input_value = json.loads(input_json)
        while True:
            current_run = self.ledger.get_run(run_id)
            if current_run is None:
                raise KeyError(f"run not found: {run_id}")
            if current_run["control_mode"] != "run":
                return current_run
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
                node_outputs = self._outputs(scope_id)
                node_outputs[node_id] = output
                node_id = definition["next"]
                self.ledger.update_run(run_id, status="running", current_node_id=node_id)
                continue

            if node["type"] == "switch":
                node_outputs = self._outputs(scope_id)
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

            if node["type"] == "repeat":
                invocation = self.ledger.get_invocation_for_node(scope_id, node_id)
                child_workflow_id = definition["workflow"]
                child_workflow = self._workflows[child_workflow_id]
                if invocation is None:
                    child_input = self._resolve_expr(
                        definition["input"],
                        input_value,
                        self._outputs(scope_id),
                    )
                    self._validate_schema(child_input, child_workflow.spec.input_schema)
                    invocation = self.ledger.create_invocation(
                        run_id,
                        scope_id,
                        node_id,
                        child_input,
                    )
                    self.ledger.finish_invocation(invocation["id"], status="running")
                    return self._start_repeat_iteration(
                        run_id,
                        scope,
                        node_id,
                        invocation,
                        child_workflow_id,
                        child_input,
                        iteration_index=1,
                    )

                if invocation["status"] == "succeeded":
                    node_id = definition["next"]
                    self.ledger.update_run(run_id, status="running", current_node_id=node_id)
                    continue
                if invocation["status"] != "running":
                    error = json.loads(invocation["error_json"] or "{}")
                    return self._fail_scope(
                        run_id,
                        scope_id,
                        node_id,
                        error or {"code": "REPEAT_FAILED", "message": "repeat invocation failed"},
                    )

                child_scopes = self.ledger.list_child_scopes(invocation["id"])
                if not child_scopes:
                    return self._fail_scope(
                        run_id,
                        scope_id,
                        node_id,
                        {
                            "code": "REPEAT_STATE_INVALID",
                            "message": "repeat invocation has no child scope",
                        },
                    )
                child_scope = child_scopes[-1]
                if child_scope["status"] == "active":
                    return self.ledger.update_run(
                        run_id,
                        status="waiting",
                        current_node_id=node_id,
                    )
                if child_scope["status"] != "succeeded" or child_scope["output_json"] is None:
                    error = json.loads(child_scope["error_json"] or "{}")
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="failed",
                        error=error
                        or {
                            "code": "REPEAT_ITERATION_FAILED",
                            "message": "repeat child scope did not succeed",
                        },
                    )
                    return self._fail_scope(
                        run_id,
                        scope_id,
                        node_id,
                        error
                        or {
                            "code": "REPEAT_ITERATION_FAILED",
                            "message": "repeat child scope did not succeed",
                        },
                    )

                iteration_index = len(child_scopes)
                iteration_output = json.loads(child_scope["output_json"])
                iteration = {"output": iteration_output, "index": iteration_index}
                self.ledger.record_event(
                    run_id,
                    "repeat.iteration.completed",
                    {
                        "nodeId": node_id,
                        "iteration": iteration_index,
                        "scopeId": child_scope["id"],
                    },
                    scope_id=scope_id,
                    invocation_id=invocation["id"],
                )
                if self._predicate(
                    definition["until"],
                    input_value,
                    self._outputs(scope_id),
                    iteration=iteration,
                ):
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="succeeded",
                        output=iteration_output,
                    )
                    node_id = definition["next"]
                    self.ledger.update_run(run_id, status="running", current_node_id=node_id)
                    continue
                if iteration_index >= definition["maxIterations"]:
                    error = {
                        "code": "LOOP_LIMIT_EXCEEDED",
                        "message": f"repeat node {node_id} reached {iteration_index} iterations",
                    }
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="failed",
                        error=error,
                    )
                    return self._fail_scope(run_id, scope_id, node_id, error)
                child_input = self._resolve_expr(
                    definition["feedback"],
                    input_value,
                    self._outputs(scope_id),
                    iteration=iteration,
                )
                self._validate_schema(child_input, child_workflow.spec.input_schema)
                return self._start_repeat_iteration(
                    run_id,
                    scope,
                    node_id,
                    invocation,
                    child_workflow_id,
                    child_input,
                    iteration_index=iteration_index + 1,
                )

            if node["type"] == "end":
                if definition["outcome"] == "succeeded":
                    output = self._resolve_expr(
                        definition["output"], input_value, self._outputs(scope_id)
                    )
                    workflow = self._workflows[scope["workflow_id"]]
                    self._validate_schema(output, workflow.spec.output_schema)
                    return self._finish_scope(
                        run_id,
                        scope_id,
                        node_id,
                        output=output,
                    )
                error = definition["error"]
                return self._fail_scope(run_id, scope_id, node_id, error)

            raise RunError(f"unsupported runtime node type: {node['type']}")

    def _execute_call(
        self,
        run_id: str,
        scope_id: str,
        node_id: str,
        definition: dict[str, Any],
        scope_input: Any,
        plan: ExecutionPlan,
    ) -> Any | None:
        input_value = self._resolve_expr(
            definition["input"],
            scope_input,
            self._outputs(scope_id),
        )
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
        try:
            self._validate_artifact_refs(run_id, input_value)
        except LedgerConflict as exc:
            error = {"code": "INPUT_ARTIFACT_INVALID", "message": str(exc)}
            self.ledger.finish_attempt(attempt["id"], status="failed", error=error)
            self.ledger.finish_invocation(invocation["id"], status="failed", error=error)
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        binding = self._binding.spec.slots[definition["slot"]]
        if binding.adapter not in {"builtin", "human"}:
            error = {"code": "EXECUTOR_UNSUPPORTED", "message": "HTTP Job runtime is not enabled."}
            self.ledger.finish_attempt(attempt["id"], status="failed", error=error)
            self.ledger.finish_invocation(invocation["id"], status="failed", error=error)
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        try:
            result = execute_builtin(binding.executor_ref, input_value, binding.config)
        except ExecutorError as exc:
            error = {"code": "EXECUTOR_FAILED", "message": str(exc)}
            self.ledger.finish_attempt(attempt["id"], status="failed", error=error)
            self.ledger.finish_invocation(invocation["id"], status="failed", error=error)
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        for observation in result.observations or []:
            self.ledger.record_event(
                run_id,
                "agent.model.completed",
                observation,
                scope_id=scope_id,
                invocation_id=invocation["id"],
                attempt_id=attempt["id"],
            )
        try:
            if result.generated_artifact is not None and result.human_request is not None:
                raise RunError(
                    "an executor result cannot include both an artifact and a human request"
                )
            if result.human_request is not None:
                request_spec = result.human_request
                subject_digest = self._artifact_subject_digest(run_id, input_value)
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
                    )
                )
                self.ledger.finish_attempt(attempt["id"], status="waiting")
                self.ledger.finish_invocation(invocation["id"], status="waiting")
                self.ledger.update_run(run_id, status="waiting", current_node_id=node_id)
                return None
            output = result.output
            self._validate_schema(output, definition["outputSchema"])
            if result.generated_artifact is not None:
                if not isinstance(output, dict):
                    raise RunError("generated artifact requires an object output")
                artifact_refs = output.get("artifact_refs", [])
                if artifact_refs != []:
                    raise LedgerConflict(
                        "managed agent output must not provide artifact references"
                    )
                artifact = self.ledger.register_artifact_content(
                    run_id=run_id,
                    content=result.generated_artifact.content,
                    name=result.generated_artifact.name,
                    media_type=result.generated_artifact.media_type,
                    invocation_id=invocation["id"],
                )
                output = dict(output)
                output["artifact_refs"] = [artifact["id"]]
            self._validate_artifact_refs(run_id, output)
        except (LedgerConflict, OSError, RunError, TypeError) as exc:
            error = {"code": "EXECUTOR_OUTPUT_INVALID", "message": str(exc)}
            self.ledger.record_event(
                run_id,
                "executor.output.rejected",
                error,
                scope_id=scope_id,
                invocation_id=invocation["id"],
                attempt_id=attempt["id"],
            )
            self.ledger.finish_attempt(attempt["id"], status="failed", error=error)
            self.ledger.finish_invocation(invocation["id"], status="failed", error=error)
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        self.ledger.finish_attempt(attempt["id"], status="succeeded", output=output)
        self.ledger.finish_invocation(invocation["id"], status="succeeded", output=output)
        return output

    def _load_schema(self, relative_path: str) -> dict[str, Any]:
        path = (self.package_dir / relative_path).resolve()
        schema, diagnostic = validate_schema_file(path, self.package_dir)
        if diagnostic is not None or schema is None:
            raise RunError(f"schema invalid: {relative_path}")
        return schema

    def _start_repeat_iteration(
        self,
        run_id: str,
        parent_scope: dict[str, Any],
        node_id: str,
        parent_invocation: dict[str, Any],
        child_workflow_id: str,
        child_input: Any,
        *,
        iteration_index: int,
    ) -> dict[str, Any]:
        path = json.loads(parent_scope["path_json"]) + [
            node_id,
            str(iteration_index),
        ]
        child_scope = self.ledger.create_scope(
            run_id,
            child_workflow_id,
            path=path,
            input_value=child_input,
            parent_scope_id=parent_scope["id"],
            parent_invocation_id=parent_invocation["id"],
        )
        self.ledger.record_event(
            run_id,
            "repeat.iteration.started",
            {
                "nodeId": node_id,
                "iteration": iteration_index,
                "scopeId": child_scope["id"],
            },
            scope_id=parent_scope["id"],
            invocation_id=parent_invocation["id"],
        )
        entry = self._workflows[child_workflow_id].spec.entry
        return self._drive(run_id, child_scope["id"], entry)

    def _finish_scope(
        self,
        run_id: str,
        scope_id: str,
        node_id: str,
        *,
        output: Any,
    ) -> dict[str, Any]:
        scope = self.ledger.finish_scope(scope_id, status="succeeded", output=output)
        if scope["parent_invocation_id"] is None:
            return self.ledger.update_run(
                run_id,
                status="succeeded",
                current_node_id=node_id,
                output=output,
            )
        parent_invocation = self.ledger.get_invocation(scope["parent_invocation_id"])
        if parent_invocation is None:
            raise RunError("parent invocation is missing")
        return self._drive(
            run_id,
            parent_invocation["scope_id"],
            parent_invocation["node_id"],
        )

    def _fail_scope(
        self,
        run_id: str,
        scope_id: str,
        node_id: str,
        error: dict[str, Any],
    ) -> dict[str, Any]:
        scope = self.ledger.get_scope(scope_id)
        if scope is None:
            raise RunError("execution scope is missing")
        if scope["status"] == "active":
            scope = self.ledger.finish_scope(scope_id, status="failed", error=error)
        if scope["parent_invocation_id"] is None:
            return self.ledger.update_run(
                run_id,
                status="failed",
                current_node_id=node_id,
                error=error,
            )
        parent_invocation = self.ledger.get_invocation(scope["parent_invocation_id"])
        if parent_invocation is None:
            raise RunError("parent invocation is missing")
        if parent_invocation["status"] == "running":
            self.ledger.finish_invocation(parent_invocation["id"], status="failed", error=error)
        return self._fail_scope(
            run_id,
            parent_invocation["scope_id"],
            parent_invocation["node_id"],
            error,
        )

    def _validate_artifact_refs(self, run_id: str, value: Any) -> None:
        self.ledger.validate_artifact_refs(run_id, self._artifact_refs(value))

    def _artifact_subject_digest(self, run_id: str, value: Any) -> str:
        refs = sorted(self._artifact_refs(value))
        self.ledger.validate_artifact_refs(run_id, refs)
        artifacts = []
        for artifact_id in refs:
            artifact = self.ledger.get_artifact(artifact_id)
            if artifact is None:
                raise LedgerConflict(f"artifact is not ready: {artifact_id}")
            artifacts.append({"id": artifact_id, "digest": artifact["digest"]})
        return _digest_json({"input": value, "artifacts": artifacts})

    @staticmethod
    def _artifact_refs(value: Any) -> list[str]:
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
        return refs

    def _outputs(self, scope_id: str) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for invocation in self.ledger.list_scope_invocations(scope_id):
            if invocation["status"] == "succeeded" and invocation["output_json"] is not None:
                outputs[invocation["node_id"]] = json.loads(invocation["output_json"])
        return outputs

    def _active_scope_for_node(self, run_id: str, node_id: str) -> dict[str, Any]:
        scopes = [
            scope
            for scope in self.ledger.list_scopes(run_id)
            if scope["status"] == "active"
        ]
        for scope in reversed(scopes):
            if node_id in self._plan(scope["workflow_id"]).nodes:
                return scope
        raise RunError(f"no active scope can resume node: {node_id}")

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
        scope_input: Any,
        outputs: dict[str, Any],
        *,
        iteration: dict[str, Any] | None = None,
    ) -> Any:
        if "literal" in expression:
            return expression["literal"]
        if "ref" in expression:
            reference = expression["ref"]
            root, _, fragment = reference.partition("#")
            if root == "input":
                value = scope_input
            elif root.startswith("nodes.") and root.endswith(".output"):
                value = outputs[root[6:-7]]
            elif root == "iteration.output" and iteration is not None:
                value = iteration["output"]
            elif root == "iteration.index" and iteration is not None:
                value = iteration["index"]
            else:
                raise RunError(f"unsupported runtime reference: {reference}")
            return _pointer(value, fragment)
        if "object" in expression:
            return {
                key: self._resolve_expr(
                    child,
                    scope_input,
                    outputs,
                    iteration=iteration,
                )
                for key, child in expression["object"].items()
            }
        if "array" in expression:
            return [
                self._resolve_expr(
                    child,
                    scope_input,
                    outputs,
                    iteration=iteration,
                )
                for child in expression["array"]
            ]
        raise RunError("invalid ValueExpr in execution plan")

    def _predicate(
        self,
        predicate: dict[str, Any],
        scope_input: Any,
        outputs: dict[str, Any],
        *,
        iteration: dict[str, Any] | None = None,
    ) -> bool:
        if "all" in predicate:
            return all(
                self._predicate(item, scope_input, outputs, iteration=iteration)
                for item in predicate["all"]
            )
        if "any" in predicate:
            return any(
                self._predicate(item, scope_input, outputs, iteration=iteration)
                for item in predicate["any"]
            )
        if "not" in predicate:
            return not self._predicate(
                predicate["not"],
                scope_input,
                outputs,
                iteration=iteration,
            )
        left = self._resolve_expr(
            predicate["left"],
            scope_input,
            outputs,
            iteration=iteration,
        )
        right = self._resolve_expr(
            predicate["right"],
            scope_input,
            outputs,
            iteration=iteration,
        )
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

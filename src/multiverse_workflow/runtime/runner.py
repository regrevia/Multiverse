from __future__ import annotations

import hashlib
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
from multiverse_workflow.runtime.http_job import (
    HttpJobClient,
    HttpJobError,
    HttpJobTransportError,
)
from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict, error_output
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry


class RunError(RuntimeError):
    """A run cannot continue because its input or execution result is invalid."""


class SchemaValidationError(RunError):
    """A runtime result does not satisfy its frozen schema."""


class Runner:
    def __init__(
        self,
        package_dir: Path,
        *,
        binding_path: Path,
        database_path: Path,
        deployment_id: str | None = None,
        namespace: str = "local",
        executor_registry: ExecutorRegistry | None = None,
    ) -> None:
        self.package_dir = package_dir.resolve()
        self.deployment_id = deployment_id
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

    def close(self) -> None:
        self.ledger.close()

    def resume_due(
        self,
        run_id: str,
        *,
        worker_id: str = "resume_due",
        wait_id: str | None = None,
    ) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        if run["status"] != "retry_wait" or run["next_attempt_at"] is None:
            return run
        now = _timestamp(datetime.now(UTC))
        if run["next_attempt_at"] > now:
            return run
        retry_waits = self.ledger.list_waits(run_id=run_id, kind="retry")
        retry_wait = next(
            (
                item
                for item in retry_waits
                if wait_id is None or item["id"] == wait_id
            ),
            None,
        )
        claimed_wait = None
        if retry_wait is not None:
            if retry_wait["status"] == "pending":
                claimed_wait = self.ledger.claim_wait(
                    retry_wait["id"],
                    worker_id=worker_id,
                    now=now,
                )
                if claimed_wait is None:
                    return run
            elif retry_wait["status"] == "claimed":
                if retry_wait["worker_id"] != worker_id:
                    return run
                claimed_wait = retry_wait
        scope_id, node_id, _invocation_id = self._continuation(run)
        try:
            resumed = self._drive(
                run_id,
                scope_id,
                node_id,
            )
        except Exception:
            if claimed_wait is not None:
                self.ledger.release_wait(claimed_wait["id"])
            raise
        if claimed_wait is not None:
            self.ledger.complete_wait(claimed_wait["id"])
        return resumed

    def sweep(
        self,
        *,
        worker_id: str,
        now: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not worker_id.strip():
            raise LedgerConflict("worker id is required")
        if limit < 1:
            raise ValueError("limit must be positive")
        now = now or _timestamp(datetime.now(UTC))
        due_waits = self.ledger.list_due_waits(
            now=now,
            namespace=self.namespace,
            limit=limit,
        )
        results: list[dict[str, Any]] = []
        for wait in due_waits:
            if wait["kind"] not in {
                "retry",
                "human-progress",
                "run-start",
                "run-resume",
                "attempt-reconcile",
                "external-submit",
                "external-observe",
            }:
                continue
            claimed = self.ledger.claim_wait(
                wait["id"],
                worker_id=worker_id,
                now=now,
            )
            if claimed is None:
                continue
            try:
                payload = json.loads(claimed["payload_json"])
                if claimed["kind"] == "retry":
                    result = self.resume_due(
                        claimed["run_id"],
                        worker_id=worker_id,
                        wait_id=claimed["id"],
                    )
                    results.append(
                        {
                            "wait_id": claimed["id"],
                            "kind": claimed["kind"],
                            "run_id": result["id"],
                            "status": result["status"],
                        }
                    )
                elif claimed["kind"] == "human-progress":
                    request_id = payload.get("requestId")
                    if not isinstance(request_id, str):
                        raise RunError("human progress wait has no request id")
                    request = self.ledger.get_human_request(request_id)
                    if request is None:
                        raise RunError("human progress request is missing")
                    result = self._resume_decided_request(request)
                    results.append(
                        {
                            "wait_id": claimed["id"],
                            "kind": claimed["kind"],
                            "run_id": result["id"],
                            "request_id": request_id,
                            "status": result["status"],
                        }
                    )
                elif claimed["kind"] == "attempt-reconcile":
                    attempt_id = payload.get("attemptId")
                    if not isinstance(attempt_id, str):
                        raise RunError("attempt reconciliation wait has no attempt id")
                    attempt = self.ledger.get_attempt(attempt_id)
                    if attempt is None or attempt["run_id"] != claimed["run_id"]:
                        raise RunError("attempt reconciliation target is missing")
                    result = self.resume_reconciled_attempt(attempt_id)
                    self.ledger.complete_wait(claimed["id"])
                    resumed_run = self.ledger.get_run(result["run_id"])
                    if resumed_run is None:
                        raise RunError("attempt reconciliation run disappeared")
                    results.append(
                        {
                            "wait_id": claimed["id"],
                            "kind": claimed["kind"],
                            "attempt_id": attempt_id,
                            "run_id": result["run_id"],
                            "status": resumed_run["status"],
                        }
                    )
                elif claimed["kind"] == "external-submit":
                    result = self._process_external_submit(claimed, payload)
                    if result["wait_status"] == "completed":
                        self.ledger.complete_wait(claimed["id"])
                    else:
                        self.ledger.reschedule_wait(
                            claimed["id"], not_before=_timestamp(datetime.now(UTC))
                        )
                    results.append(result)
                elif claimed["kind"] == "external-observe":
                    result = self._process_external_observe(claimed, payload)
                    if result["wait_status"] == "completed":
                        self.ledger.complete_wait(claimed["id"])
                    else:
                        self.ledger.reschedule_wait(
                            claimed["id"], not_before=_timestamp(datetime.now(UTC))
                        )
                    results.append(result)
                else:
                    result = self.resume_queued(claimed["run_id"])
                    self.ledger.complete_wait(claimed["id"])
                    results.append(
                        {
                            "wait_id": claimed["id"],
                            "kind": claimed["kind"],
                            "run_id": result["id"],
                            "status": result["status"],
                        }
                    )
            except Exception:
                self.ledger.release_wait(claimed["id"])
                raise
        # A crash can occur after the queued Run transaction and before its
        # wake record is written. Recover those Runs without creating another
        # Scope, Invocation, or Attempt.
        for run in self.ledger.list_queued_runs(
            namespace=self.namespace,
            limit=max(0, limit - len(results)),
        ) if len(results) < limit else []:
            start_wait = self.ledger.get_wait_by_key(
                self.namespace, f"run-start:{run['id']}"
            )
            if start_wait is not None:
                continue
            result = self.resume_queued(run["id"])
            results.append(
                {
                    "kind": "run-start-recovery",
                    "run_id": result["id"],
                    "status": result["status"],
                }
            )
        return results

    def _process_external_submit(
        self,
        wait: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        outbox_id = payload.get("outboxId")
        attempt_id = payload.get("attemptId")
        if not isinstance(outbox_id, str) or not isinstance(attempt_id, str):
            raise RunError("external submit wait has invalid payload")
        outbox = self.ledger.get_outbox(outbox_id)
        attempt = self.ledger.get_attempt(attempt_id)
        if outbox is None or attempt is None:
            raise RunError("external submit target is missing")
        if outbox["status"] == "submitted" and outbox["external_ref"]:
            self.ledger.ensure_external_observation_wait(
                attempt_id=attempt_id,
                external_ref=outbox["external_ref"],
            )
            return {
                "wait_id": wait["id"],
                "kind": wait["kind"],
                "attempt_id": attempt_id,
                "run_id": attempt["run_id"],
                "status": "submitted",
                "wait_status": "completed",
            }
        request = json.loads(outbox["payload_json"])
        client = self._http_job_client(attempt_id)
        if outbox["status"] == "unknown":
            lookup = client.lookup(attempt["dispatch_key"])
            if lookup.get("status") == "found" and isinstance(
                lookup.get("executionRef"), str
            ):
                self.ledger.resolve_unknown_submit(
                    outbox_id,
                    external_ref=lookup["executionRef"],
                    evidence=lookup,
                )
                self.ledger.ensure_external_observation_wait(
                    attempt_id=attempt_id,
                    external_ref=lookup["executionRef"],
                )
                return {
                    "wait_id": wait["id"],
                    "kind": wait["kind"],
                    "attempt_id": attempt_id,
                    "run_id": attempt["run_id"],
                    "status": "submitted",
                    "wait_status": "completed",
                }
            if lookup.get("status") != "not_created":
                raise RunError("HTTP Job submit result remains unknown")
            descriptor = client.describe()
            if descriptor.get("reconcileByKey") != "strong":
                raise RunError(
                    "HTTP Job strong lookup is required to prove not_created"
                )
            self.ledger.mark_submit_outbox_retryable(outbox_id)
        claimed = self.ledger.claim_submit_outbox(outbox_id)
        try:
            response = client.submit(request)
        except HttpJobTransportError as exc:
            self.ledger.mark_submit_outbox_unknown(
                outbox_id,
                error={"code": "SUBMIT_RESULT_UNKNOWN", "message": str(exc)},
            )
            lookup = client.lookup(attempt["dispatch_key"])
            if lookup.get("status") == "found" and isinstance(
                lookup.get("executionRef"), str
            ):
                self.ledger.resolve_unknown_submit(
                    outbox_id,
                    external_ref=lookup["executionRef"],
                    evidence=lookup,
                )
                self.ledger.ensure_external_observation_wait(
                    attempt_id=attempt_id,
                    external_ref=lookup["executionRef"],
                )
                return {
                    "wait_id": wait["id"],
                    "kind": wait["kind"],
                    "attempt_id": attempt_id,
                    "run_id": attempt["run_id"],
                    "status": "submitted",
                    "wait_status": "completed",
                }
            if lookup.get("status") == "not_created":
                descriptor = client.describe()
                if descriptor.get("reconcileByKey") != "strong":
                    raise RunError(
                        "HTTP Job strong lookup is required to prove not_created"
                    ) from exc
                self.ledger.mark_submit_outbox_retryable(outbox_id)
                raise exc
            raise
        except HttpJobError:
            self.ledger.mark_submit_outbox_unknown(
                outbox_id,
                error={"code": "SUBMIT_FAILED", "message": "HTTP Job submit failed"},
            )
            raise
        external_ref = response["executionRef"]
        self.ledger.mark_submit_outbox_submitted(outbox_id, external_ref=external_ref)
        self.ledger.ensure_external_observation_wait(
            attempt_id=attempt_id,
            external_ref=external_ref,
        )
        return {
            "wait_id": wait["id"],
            "kind": wait["kind"],
            "attempt_id": attempt_id,
            "run_id": attempt["run_id"],
            "status": claimed["status"],
            "wait_status": "completed",
        }

    def _process_external_observe(
        self,
        wait: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        attempt_id = payload.get("attemptId")
        external_ref = payload.get("externalRef")
        if not isinstance(attempt_id, str) or not isinstance(external_ref, str):
            raise RunError("external observe wait has invalid payload")
        attempt = self.ledger.get_attempt(attempt_id)
        if attempt is None:
            raise RunError("external observe attempt is missing")
        observation = self._http_job_client(attempt_id).observe(external_ref)
        try:
            self.ledger.record_external_observation(attempt_id, observation=observation)
        except LedgerConflict as exc:
            error = {"code": "EXECUTOR_PROTOCOL_VIOLATION", "message": str(exc)}
            run = self.ledger.get_run(attempt["run_id"])
            if run is None:
                raise RunError("external observation run is missing") from exc
            self.ledger.record_event(
                run["id"],
                "executor.observation.rejected",
                {
                    "attemptId": attempt_id,
                    "externalRef": external_ref,
                    "observation": observation,
                    "error": error,
                },
                scope_id=attempt["scope_id"],
                invocation_id=attempt["invocation_id"],
                attempt_id=attempt_id,
            )
            self.ledger.update_run(
                run["id"],
                status="blocked",
                current_scope_id=attempt["scope_id"],
                current_node_id=self._attempt_node(attempt),
                current_invocation_id=attempt["invocation_id"],
                error=error,
            )
            return {
                "wait_id": wait["id"],
                "kind": wait["kind"],
                "attempt_id": attempt_id,
                "run_id": attempt["run_id"],
                "status": "blocked",
                "wait_status": "completed",
            }
        status = observation.get("status")
        final = observation.get("executionFinal") is True
        result = {
            "wait_id": wait["id"],
            "kind": wait["kind"],
            "attempt_id": attempt_id,
            "run_id": attempt["run_id"],
            "status": status,
            "wait_status": "pending",
        }
        if not final:
            return result
        if status == "unknown":
            error = {
                "code": "EXECUTION_RESULT_UNKNOWN",
                "message": (
                    "HTTP Job returned a final unknown observation; "
                    "reconciliation is required."
                ),
            }
            self.ledger.finish_attempt(
                attempt_id,
                status="unknown",
                error=error,
                external_ref=external_ref,
            )
            result["status"] = "unknown"
            result["wait_status"] = "completed"
            return result
        if status == "succeeded":
            output = observation.get("output")
            scope = self.ledger.get_scope(attempt["scope_id"])
            run = self.ledger.get_run(attempt["run_id"])
            if scope is None or run is None:
                raise RunError("external observation runtime state is missing")
            plan = self._frozen_plan(run, scope["workflow_id"])
            invocation = self.ledger.get_invocation(attempt["invocation_id"])
            if invocation is None:
                raise RunError("external observation invocation is missing")
            node = plan.nodes[invocation["node_id"]]
            self._validate_schema(output, node["definition"]["outputSchema"])
            self._validate_artifact_refs(run["id"], output)
            self.ledger.finish_attempt(attempt_id, status="succeeded", output=output)
            self.ledger.finish_invocation(invocation["id"], status="succeeded", output=output)
            next_node = node["definition"]["next"]
            self.ledger.update_run(
                run["id"],
                status="running",
                current_scope_id=scope["id"],
                current_node_id=next_node,
                current_invocation_id=None,
            )
            self._drive(run["id"], scope["id"], next_node)
            result["status"] = "succeeded"
            result["wait_status"] = "completed"
            return result
        remote_error = observation.get("error")
        if not isinstance(remote_error, dict):
            remote_error = {
                "code": "REMOTE_EXECUTION_FAILED",
                "message": "HTTP Job failed",
            }
        invocation = self.ledger.get_invocation(attempt["invocation_id"])
        if invocation is None:
            raise RunError("external observation invocation is missing")
        scope = self.ledger.get_scope(attempt["scope_id"])
        run = self.ledger.get_run(attempt["run_id"])
        if scope is None or run is None:
            raise RunError("external observation runtime state is missing")
        plan = self._frozen_plan(run, scope["workflow_id"])
        node = plan.nodes[invocation["node_id"]]
        self._record_call_failure(attempt, invocation, remote_error)
        if self._schedule_retry(
            run["id"],
            scope["id"],
            invocation["node_id"],
            node["definition"],
            invocation,
            attempt,
            remote_error,
        ):
            result["status"] = status
            result["wait_status"] = "completed"
            return result
        self._fail_scope(
            attempt["run_id"],
            attempt["scope_id"],
            self._attempt_node(attempt),
            remote_error,
        )
        result["status"] = status
        result["wait_status"] = "completed"
        return result

    def _attempt_node(self, attempt: dict[str, Any]) -> str:
        invocation = self.ledger.get_invocation(attempt["invocation_id"])
        if invocation is None:
            raise RunError("attempt invocation is missing")
        return str(invocation["node_id"])

    def _http_job_client(self, attempt_id: str) -> HttpJobClient:
        attempt = self.ledger.get_attempt(attempt_id)
        if attempt is None:
            raise RunError("HTTP Job attempt is missing")
        invocation = self.ledger.get_invocation(attempt["invocation_id"])
        run = self.ledger.get_run(attempt["run_id"])
        if invocation is None or run is None:
            raise RunError("HTTP Job runtime state is missing")
        scope = self.ledger.get_scope(attempt["scope_id"])
        if scope is None:
            raise RunError("HTTP Job scope is missing")
        plan = self._frozen_plan(run, scope["workflow_id"])
        definition = plan.nodes[invocation["node_id"]]["definition"]
        binding = self._binding.spec.slots[definition["slot"]]
        base_url = binding.config.get("baseUrl")
        if not isinstance(base_url, str) or not base_url.strip():
            raise RunError("HTTP Job binding requires config.baseUrl")
        timeout = binding.config.get("timeoutSeconds", 30)
        if not isinstance(timeout, (int, float)):
            raise RunError("HTTP Job timeoutSeconds must be numeric")
        return HttpJobClient(base_url, timeout_seconds=float(timeout))

    def start(
        self,
        input_value: Any,
        workflow_id: str | None = None,
        *,
        run_id: str | None = None,
        rerun_of: str | None = None,
        rerun_reason: str | None = None,
        command_id: str | None = None,
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
            deployment_id=self.deployment_id,
            workflow_id=workflow_id,
            package_digest=plan.package_digest,
            binding_digest=plan.binding_digest,
            plan={
                "rootWorkflowId": workflow_id,
                "workflows": {
                    candidate_id: candidate_plan.as_dict()
                    for candidate_id, candidate_plan in self._plans.items()
                },
            },
            input_value=input_value,
            deadline_at=_timestamp(deadline),
            run_id=run_id,
            rerun_of=rerun_of,
            rerun_reason=rerun_reason,
            command_id=command_id,
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
            current_scope_id=scope["id"],
            current_node_id=workflow.spec.entry,
            current_invocation_id=None,
        )
        return self._drive(run["id"], scope["id"], workflow.spec.entry)

    def enqueue(
        self,
        input_value: Any,
        workflow_id: str | None = None,
        *,
        run_id: str | None = None,
        rerun_of: str | None = None,
        rerun_reason: str | None = None,
        command_id: str | None = None,
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
        return self.ledger.create_queued_run(
            namespace=self.namespace,
            deployment_id=self.deployment_id,
            workflow_id=workflow_id,
            package_digest=plan.package_digest,
            binding_digest=plan.binding_digest,
            plan={
                "rootWorkflowId": workflow_id,
                "workflows": {
                    candidate_id: candidate_plan.as_dict()
                    for candidate_id, candidate_plan in self._plans.items()
                },
            },
            input_value=input_value,
            deadline_at=_timestamp(deadline),
            entry_node_id=workflow.spec.entry,
            run_id=run_id,
            rerun_of=rerun_of,
            rerun_reason=rerun_reason,
            command_id=command_id,
        )

    def resume_queued(self, run_id: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        if run["status"] in {
            "waiting",
            "retry_wait",
            "paused",
            "succeeded",
            "failed",
            "cancelled",
            "blocked",
        }:
            return run
        scope_id, node_id, _invocation_id = self._continuation(run)
        if run["status"] == "queued":
            run = self.ledger.update_run(
                run_id,
                status="running",
                current_scope_id=scope_id,
                current_node_id=node_id,
                current_invocation_id=run["current_invocation_id"],
            )
        return self._drive(run_id, scope_id, node_id)

    def pending_human_requests(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return self.ledger.list_human_requests(run_id=run_id, status="pending")

    def inspect(self, run_id: str) -> dict[str, Any] | None:
        return self.ledger.get_run(run_id)

    def pause(
        self,
        run_id: str,
        *,
        expected_version: int,
        reason: str,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        return self.ledger.control_run(
            run_id,
            operation="pause",
            expected_version=expected_version,
            reason=reason,
            command_id=command_id,
        )

    def resume(
        self,
        run_id: str,
        *,
        expected_version: int,
        reason: str,
        command_id: str | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        self._require_matching_definition(run, self._plan(run["workflow_id"]))
        resumed = self.ledger.control_run(
            run_id,
            operation="resume",
            expected_version=expected_version,
            reason=reason,
            command_id=command_id,
            enqueue_resume=not resume,
        )
        scope_id, node_id, _invocation_id = self._continuation(resumed)
        if node_id is None:
            return resumed
        if not resume:
            return resumed
        return self._drive(run_id, scope_id, node_id)

    def cancel(
        self,
        run_id: str,
        *,
        expected_version: int,
        reason: str,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        return self.ledger.control_run(
            run_id,
            operation="cancel",
            expected_version=expected_version,
            reason=reason,
            command_id=command_id,
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
        command_id: str | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        request = self.ledger.get_human_request(request_id)
        if request is None:
            raise KeyError(f"human request not found: {request_id}")
        if idempotency_key is not None:
            previous = self.ledger.get_human_decision_by_idempotency_key(idempotency_key)
            if previous is not None:
                if previous["request_id"] != request_id:
                    raise LedgerConflict("idempotency key belongs to another request")
                return self._resume_decided_request(request, resume=resume)
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
        plan = self._frozen_plan(run, scope["workflow_id"])
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
            command_id=command_id,
        )
        return self._resume_decided_request(request, resume=resume)

    def reconcile_attempt(
        self,
        attempt_id: str,
        *,
        expected_version: int,
        conclusion: str,
        evidence_refs: list[str],
        reason: str,
        actor: str,
        output: Any = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        attempt = self.ledger.get_attempt(attempt_id)
        if attempt is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        if attempt["status"] != "unknown":
            raise LedgerConflict(
                f"only an unknown attempt can be reconciled: {attempt['status']}"
            )
        latest_attempt = self.ledger.latest_attempt(attempt["invocation_id"])
        if latest_attempt is None or latest_attempt["id"] != attempt_id:
            raise LedgerConflict("only the latest attempt can be reconciled")
        invocation = self.ledger.get_invocation(attempt["invocation_id"])
        run = self.ledger.get_run(attempt["run_id"])
        scope = self.ledger.get_scope(attempt["scope_id"])
        if invocation is None or run is None or scope is None:
            raise RunError("reconciled attempt references missing runtime state")
        if run["status"] in {"succeeded", "failed", "cancelled"}:
            raise LedgerConflict("cannot reconcile an attempt from a terminal run")
        if invocation["status"] != "reconciling":
            raise LedgerConflict(
                f"attempt invocation is not reconciling: {invocation['status']}"
            )
        if (
            run["current_scope_id"] != attempt["scope_id"]
            or run["current_node_id"] != invocation["node_id"]
            or run["current_invocation_id"] not in {None, invocation["id"]}
        ):
            raise LedgerConflict("attempt is not the current run node")
        self._require_matching_definition(run, self._plan(run["workflow_id"]))
        plan = self._frozen_plan(run, scope["workflow_id"])
        node = plan.nodes.get(invocation["node_id"])
        if node is None:
            raise RunError("reconciled invocation node is missing from the frozen plan")
        if conclusion == "confirmed_succeeded":
            binding = self._binding.spec.slots[node["definition"]["slot"]]
            if binding.adapter == "human":
                raise LedgerConflict(
                    "human invocation requires a human decision and cannot be "
                    "reconciled as succeeded"
                )
        if conclusion not in {
            "confirmed_succeeded",
            "confirmed_failed",
            "confirmed_cancelled",
            "confirmed_not_started",
        }:
            raise LedgerConflict(f"unsupported reconciliation conclusion: {conclusion}")
        if conclusion == "confirmed_succeeded":
            self._validate_schema(output, node["definition"]["outputSchema"])
            self._validate_artifact_refs(run["id"], output)
        reconciled = self.ledger.reconcile_attempt(
            attempt_id,
            expected_version=expected_version,
            conclusion=conclusion,  # type: ignore[arg-type]
            evidence_refs=evidence_refs,
            reason=reason,
            actor=actor,
            output=output,
            enqueue_wait=not resume,
        )
        if not resume:
            return reconciled
        return self._apply_reconciled_attempt(reconciled)

    def resume_reconciled_attempt(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.ledger.get_attempt(attempt_id)
        if attempt is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        if attempt["reconciliation_json"] is None:
            raise LedgerConflict("attempt has no persisted reconciliation")
        if attempt["status"] == "unknown":
            raise LedgerConflict("attempt reconciliation is not committed")
        run = self.ledger.get_run(attempt["run_id"])
        if run is None:
            raise RunError("reconciled attempt run is missing")
        self._require_matching_definition(run, self._plan(run["workflow_id"]))
        return self._apply_reconciled_attempt(attempt)

    def _apply_reconciled_attempt(self, attempt: dict[str, Any]) -> dict[str, Any]:
        reconciliation = json.loads(attempt["reconciliation_json"] or "{}")
        conclusion = reconciliation.get("conclusion")
        invocation = self.ledger.get_invocation(attempt["invocation_id"])
        run = self.ledger.get_run(attempt["run_id"])
        scope = self.ledger.get_scope(attempt["scope_id"])
        if invocation is None or run is None or scope is None:
            raise RunError("reconciled attempt references missing runtime state")
        if run["status"] in {"succeeded", "failed", "cancelled"}:
            return attempt
        if (
            run["current_scope_id"] is None
            or run["current_node_id"] is None
        ):
            raise RunError("run has no matching persisted continuation for reconciliation")
        if (
            run["current_scope_id"] != attempt["scope_id"]
            or run["current_node_id"] != invocation["node_id"]
            or run["current_invocation_id"] not in {None, invocation["id"]}
        ):
            return attempt
        plan = self._frozen_plan(run, scope["workflow_id"])
        node = plan.nodes.get(invocation["node_id"])
        if node is None:
            raise RunError("reconciled invocation node is missing from the frozen plan")
        if conclusion == "confirmed_succeeded":
            output = json.loads(attempt["output_json"] or "null")
            if invocation["status"] != "succeeded":
                self.ledger.finish_invocation(
                    invocation["id"],
                    status="succeeded",
                    output=output,
                )
            if run["control_mode"] == "cancel":
                self._cancel_scope(
                    run["id"],
                    attempt["scope_id"],
                    invocation["node_id"],
                    {
                        "code": "RUN_CANCELLED",
                        "message": "Run cancellation was requested before downstream dispatch.",
                    },
                )
                return attempt
            next_node = node["definition"]["next"]
            if (
                run["current_scope_id"] != attempt["scope_id"]
                or run["current_node_id"] != invocation["node_id"]
                or run["current_invocation_id"] not in {None, invocation["id"]}
            ):
                return attempt
            if run["control_mode"] == "pause":
                self.ledger.update_run(
                    run["id"],
                    status="paused",
                    control_mode="pause",
                    current_scope_id=attempt["scope_id"],
                    current_node_id=next_node,
                    current_invocation_id=None,
                )
                return attempt
            self.ledger.update_run(
                run["id"],
                status="running",
                current_scope_id=attempt["scope_id"],
                current_node_id=next_node,
                current_invocation_id=None,
            )
            self._drive(run["id"], attempt["scope_id"], next_node)
        elif conclusion == "confirmed_not_started":
            if invocation["status"] in {"succeeded", "failed", "cancelled"}:
                return attempt
            max_attempts = int(
                node["defaults"]["retry"].get("maxAttempts", 1)
            )
            if (
                run["control_mode"] != "cancel"
                and attempt["attempt_no"] < max_attempts
            ):
                latest_attempt = self.ledger.latest_attempt(invocation["id"])
                if latest_attempt is None:
                    raise RunError("reconciled invocation has no attempt history")
                if latest_attempt["id"] == attempt["id"]:
                    self.ledger.create_attempt(
                        invocation["id"],
                        input_value=json.loads(invocation["input_json"]),
                        dispatch_key=(
                            f"{invocation['id']}:{attempt['attempt_no'] + 1}"
                        ),
                        effect_key=attempt["effect_key"],
                        attempt_no=attempt["attempt_no"] + 1,
                    )
                else:
                    if latest_attempt["effect_key"] != attempt["effect_key"]:
                        raise RunError(
                            "reconciled retry changed the invocation effect key"
                        )
                if invocation["status"] != "running":
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="running",
                    )
                if run["control_mode"] == "pause":
                    self.ledger.update_run(
                        run["id"],
                        status="paused",
                        control_mode="pause",
                        current_scope_id=attempt["scope_id"],
                        current_node_id=invocation["node_id"],
                        current_invocation_id=invocation["id"],
                    )
                else:
                    self.ledger.update_run(
                        run["id"],
                        status="running",
                        current_scope_id=attempt["scope_id"],
                        current_node_id=invocation["node_id"],
                        current_invocation_id=invocation["id"],
                    )
                    self._drive(
                        run["id"],
                        attempt["scope_id"],
                        invocation["node_id"],
                    )
                return attempt
            error = json.loads(attempt["error_json"] or "{}")
            if run["control_mode"] == "cancel":
                if invocation["status"] != "cancelled":
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="cancelled",
                        output=error_output(error),
                        error=error,
                    )
                self._cancel_scope(
                    run["id"],
                    attempt["scope_id"],
                    invocation["node_id"],
                    error,
                )
                return attempt
            if invocation["status"] != "failed":
                self.ledger.finish_invocation(
                    invocation["id"],
                    status="failed",
                    output=error_output(error),
                    error=error,
                )
            self._fail_scope(
                run["id"],
                attempt["scope_id"],
                invocation["node_id"],
                error,
                route_on_error=False,
            )
        elif conclusion in {
            "confirmed_failed",
            "confirmed_cancelled",
        }:
            error = json.loads(attempt["error_json"] or "{}")
            if conclusion == "confirmed_failed":
                if invocation["status"] != "failed":
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="failed",
                        output=error_output(error),
                        error=error,
                    )
                self._fail_scope(
                    run["id"],
                    attempt["scope_id"],
                    invocation["node_id"],
                    error,
                )
            else:
                if invocation["status"] != "cancelled":
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="cancelled",
                        output=error_output(error),
                        error=error,
                    )
                self._cancel_scope(
                    run["id"],
                    attempt["scope_id"],
                    invocation["node_id"],
                    error,
                )
        return attempt

    def _resume_decided_request(
        self, request: dict[str, Any], *, resume: bool = True
    ) -> dict[str, Any]:
        intent = self.ledger.get_human_progress_intent(request["id"])
        if intent is None:
            intent = self.ledger.ensure_human_progress_intent(request["id"])
        if intent["status"] == "completed":
            run = self.ledger.get_run(request["run_id"])
            if run is None:
                raise RunError("human request run is missing")
            return run
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
        plan = self._frozen_plan(run, scope["workflow_id"])
        if invocation["status"] not in {"waiting", "succeeded"}:
            raise RunError(f"human request invocation cannot resume: {invocation['status']}")
        attempt = self.ledger.latest_attempt(invocation["id"])
        decision = self.ledger.get_human_decision(request["id"])
        if attempt is None or decision is None:
            raise RunError("human decision ledger records are incomplete")
        if invocation["status"] == "waiting":
            if request["request_type"] in {"approval", "review"}:
                output = {
                    "decision": decision["choice"],
                    "comment": decision["comment"],
                }
            else:
                output = json.loads(decision["decision_json"])
            if attempt["status"] != "succeeded":
                self.ledger.finish_attempt(
                    attempt["id"],
                    status="succeeded",
                    output=output,
                )
            self.ledger.finish_invocation(
                invocation["id"],
                status="succeeded",
                output=output,
            )
            invocation = self.ledger.get_invocation(invocation["id"])
            if invocation is None:
                raise RunError("human request invocation disappeared")
        if not resume:
            current = self.ledger.get_run(request["run_id"])
            if current is None:
                raise RunError("human request run is missing")
            return current
        run = self.ledger.get_run(run["id"])
        if run is None:
            raise RunError("human request run is missing")
        if run["current_scope_id"] is None or run["current_node_id"] is None:
            raise RunError("run has no persisted continuation for human decision")
        node = plan.nodes[invocation["node_id"]]
        next_node = node["definition"]["next"]
        if run["status"] in {"succeeded", "failed", "cancelled"}:
            self.ledger.complete_human_progress_intent(request["id"])
            return run
        continuation_scope_id = run["current_scope_id"]
        continuation_node_id = run["current_node_id"]
        continuation_invocation_id = run["current_invocation_id"]
        if (
            continuation_scope_id != invocation["scope_id"]
            or continuation_node_id != invocation["node_id"]
            or continuation_invocation_id not in {None, invocation["id"]}
        ):
            if (
                run["status"] == "running"
                and run["control_mode"] == "run"
                and continuation_scope_id is not None
                and continuation_node_id is not None
            ):
                resumed = self._drive(
                    run["id"],
                    continuation_scope_id,
                    continuation_node_id,
                )
                self.ledger.complete_human_progress_intent(request["id"])
                return resumed
            self.ledger.complete_human_progress_intent(request["id"])
            return run
        if run["control_mode"] == "pause":
            self.ledger.update_run(
                run["id"],
                status="paused",
                control_mode="pause",
                current_scope_id=invocation["scope_id"],
                current_node_id=next_node,
                current_invocation_id=None,
            )
            paused = self.ledger.get_run(run["id"])
            if paused is None:
                raise RunError("human request run disappeared")
            self.ledger.complete_human_progress_intent(request["id"])
            return paused
        self.ledger.update_run(
            run["id"],
            status="running",
            current_scope_id=invocation["scope_id"],
            current_node_id=next_node,
            current_invocation_id=None,
        )
        resumed = self._drive(run["id"], invocation["scope_id"], next_node)
        self.ledger.complete_human_progress_intent(request["id"])
        return resumed

    def _drive(self, run_id: str, scope_id: str, node_id: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        scope = self.ledger.get_scope(scope_id)
        if scope is None:
            raise RunError("execution scope is missing")
        if run["control_mode"] != "run":
            return run
        if run["status"] == "retry_wait":
            next_attempt_at = run["next_attempt_at"]
            if next_attempt_at is not None and next_attempt_at > _timestamp(datetime.now(UTC)):
                return run
            self.ledger.update_run(
                run_id,
                status="running",
                current_scope_id=scope_id,
                current_node_id=node_id,
                current_invocation_id=None,
                next_attempt_at=None,
            )
        plan = self._frozen_plan(run, scope["workflow_id"])
        input_json = scope["input_json"] or run["input_json"]
        input_value = json.loads(input_json)
        while True:
            current_run = self.ledger.get_run(run_id)
            if current_run is None:
                raise KeyError(f"run not found: {run_id}")
            if current_run["control_mode"] != "run":
                return current_run
            current_invocation = self.ledger.get_invocation_for_node(scope_id, node_id)
            if (
                current_run["current_scope_id"] != scope_id
                or current_run["current_node_id"] != node_id
                or current_run["current_invocation_id"]
                != (current_invocation["id"] if current_invocation is not None else None)
            ):
                current_run = self.ledger.update_run(
                    run_id,
                    status=current_run["status"],
                    current_scope_id=scope_id,
                    current_node_id=node_id,
                    current_invocation_id=(
                        current_invocation["id"]
                        if current_invocation is not None
                        else None
                    ),
                )
            node = plan.nodes[node_id]
            definition = node["definition"]
            if node["type"] == "call":
                invocation = self.ledger.get_invocation_for_node(scope_id, node_id)
                if invocation is not None and invocation["status"] == "waiting":
                    return self.ledger.update_run(
                        run_id,
                        status="waiting",
                        current_scope_id=scope_id,
                        current_node_id=node_id,
                        current_invocation_id=invocation["id"],
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
                        invocation=invocation,
                    )
                    if output is None:
                        return self.ledger.get_run(run_id)  # type: ignore[return-value]
                node_outputs = self._outputs(scope_id)
                node_outputs[node_id] = output
                node_id = definition["next"]
                self.ledger.update_run(
                    run_id,
                    status="running",
                    current_scope_id=scope_id,
                    current_node_id=node_id,
                    current_invocation_id=None,
                )
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
                self.ledger.update_run(
                    run_id,
                    status="running",
                    current_scope_id=scope_id,
                    current_node_id=node_id,
                    current_invocation_id=None,
                )
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
                    current_run = self.ledger.get_run(run_id)
                    if current_run is None:
                        raise RunError("run disappeared while creating repeat invocation")
                    self.ledger.update_run(
                        run_id,
                        status=current_run["status"],
                        current_scope_id=scope_id,
                        current_node_id=node_id,
                        current_invocation_id=invocation["id"],
                    )
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
                    self.ledger.update_run(
                        run_id,
                        status="running",
                        current_scope_id=scope_id,
                        current_node_id=node_id,
                        current_invocation_id=None,
                    )
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
                        current_scope_id=scope_id,
                        current_node_id=node_id,
                        current_invocation_id=invocation["id"],
                    )
                if child_scope["status"] != "succeeded" or child_scope["output_json"] is None:
                    error = json.loads(child_scope["error_json"] or "{}")
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="failed",
                        output=error_output(
                            error
                            or {
                                "code": "REPEAT_ITERATION_FAILED",
                                "message": "repeat child scope did not succeed",
                            }
                        ),
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
                    self.ledger.update_run(
                        run_id,
                        status="running",
                        current_scope_id=scope_id,
                        current_node_id=node_id,
                        current_invocation_id=None,
                    )
                    continue
                if iteration_index >= definition["maxIterations"]:
                    error = {
                        "code": "LOOP_LIMIT_EXCEEDED",
                        "message": f"repeat node {node_id} reached {iteration_index} iterations",
                    }
                    self.ledger.finish_invocation(
                        invocation["id"],
                        status="failed",
                        output=error_output(error),
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
        *,
        invocation: dict[str, Any] | None = None,
    ) -> Any | None:
        if invocation is None:
            input_value = self._resolve_expr(
                definition["input"],
                scope_input,
                self._outputs(scope_id),
            )
        else:
            input_value = json.loads(invocation["input_json"])
        self._validate_schema(input_value, definition["inputSchema"])
        if invocation is None:
            invocation = self.ledger.create_invocation(
                run_id,
                scope_id,
                node_id,
                input_value,
            )
            current_run = self.ledger.get_run(run_id)
            if current_run is None:
                raise RunError("run disappeared while creating invocation")
            self.ledger.update_run(
                run_id,
                status=current_run["status"],
                current_scope_id=scope_id,
                current_node_id=node_id,
                current_invocation_id=invocation["id"],
            )
        attempt = self.ledger.latest_attempt(invocation["id"])
        if attempt is None:
            attempt = self.ledger.create_attempt(
                invocation["id"],
                input_value=input_value,
                dispatch_key=f"{invocation['id']}:1",
                effect_key=invocation["id"],
            )
        elif invocation["status"] == "retry_wait" and attempt["status"] == "failed":
            attempt = self.ledger.create_attempt(
                invocation["id"],
                input_value=input_value,
                dispatch_key=f"{invocation['id']}:{attempt['attempt_no'] + 1}",
                effect_key=attempt["effect_key"],
                attempt_no=attempt["attempt_no"] + 1,
            )
            self.ledger.finish_invocation(invocation["id"], status="running")
        elif attempt["status"] == "unknown":
            raise LedgerConflict("unknown attempt requires reconciliation before dispatch")
        elif attempt["status"] in {"succeeded", "failed", "cancelled"}:
            raise RunError(
                f"invocation has no dispatchable attempt: {attempt['status']}"
            )
        try:
            self._validate_artifact_refs(run_id, input_value)
        except LedgerConflict as exc:
            error = {"code": "INPUT_ARTIFACT_INVALID", "message": str(exc)}
            self._record_call_failure(attempt, invocation, error)
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        binding = self._binding.spec.slots[definition["slot"]]
        if binding.adapter == "http_job":
            if attempt["external_ref"]:
                self.ledger.ensure_external_observation_wait(
                    attempt_id=attempt["id"],
                    external_ref=attempt["external_ref"],
                )
                return None
            execution_request = self._build_http_execution_request(
                run_id=run_id,
                scope_id=scope_id,
                invocation=invocation,
                attempt=attempt,
                definition=definition,
                input_value=input_value,
                plan=plan,
                binding=binding,
            )
            self.ledger.ensure_submit_outbox(
                attempt_id=attempt["id"],
                payload=execution_request,
            )
            return None
        if binding.adapter not in {"builtin", "human"}:
            error = {
                "code": "EXECUTOR_UNSUPPORTED",
                "message": f"adapter is not enabled: {binding.adapter}",
            }
            self._record_call_failure(attempt, invocation, error)
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        try:
            result = execute_builtin(binding.executor_ref, input_value, binding.config)
        except ExecutorError as exc:
            error = {"code": "EXECUTOR_FAILED", "message": str(exc)}
            self._record_call_failure(attempt, invocation, error)
            if self._schedule_retry(
                run_id,
                scope_id,
                node_id,
                definition,
                invocation,
                attempt,
                error,
            ):
                return None
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
                self.ledger.update_run(
                    run_id,
                    status="waiting",
                    current_scope_id=scope_id,
                    current_node_id=node_id,
                    current_invocation_id=invocation["id"],
                )
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
            self._record_call_failure(attempt, invocation, error)
            if self._schedule_retry(
                run_id,
                scope_id,
                node_id,
                definition,
                invocation,
                attempt,
                error,
            ):
                return None
            self._fail_scope(run_id, scope_id, node_id, error)
            return None
        self.ledger.finish_attempt(attempt["id"], status="succeeded", output=output)
        self.ledger.finish_invocation(invocation["id"], status="succeeded", output=output)
        return output

    def _build_http_execution_request(
        self,
        *,
        run_id: str,
        scope_id: str,
        invocation: dict[str, Any],
        attempt: dict[str, Any],
        definition: dict[str, Any],
        input_value: Any,
        plan: ExecutionPlan,
        binding: Any,
    ) -> dict[str, Any]:
        input_json = json.dumps(
            input_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        input_schema = self._load_schema(definition["inputSchema"])
        output_schema = self._load_schema(definition["outputSchema"])
        return {
            "protocolVersion": "multiverse/v0.1",
            "dispatchKey": attempt["dispatch_key"],
            "effectKey": attempt["effect_key"],
            "runId": run_id,
            "scopeId": scope_id,
            "invocationId": invocation["id"],
            "attemptId": attempt["id"],
            "attemptNo": attempt["attempt_no"],
            "executorRef": binding.executor_ref,
            "input": input_value,
            "inputDigest": f"sha256:{hashlib.sha256(input_json.encode('utf-8')).hexdigest()}",
            "inputSchemaDigest": _schema_digest(input_schema),
            "outputSchemaDigest": _schema_digest(output_schema),
            "deadlineAt": self._require_run_for_request(run_id)["deadline_at"],
            "authorizationRef": str(binding.secret_refs.get("authorization", "local-grant")),
            "context": {
                "artifactRefs": sorted(self._artifact_refs(input_value)),
                "handoff": None,
                "promptRefs": [],
                "skillRefs": [],
            },
            "traceContext": None,
        }

    def _require_run_for_request(self, run_id: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise RunError("HTTP Job run is missing")
        return run

    def _record_call_failure(
        self,
        attempt: dict[str, Any],
        invocation: dict[str, Any],
        error: dict[str, Any],
    ) -> None:
        envelope = error_output(error)
        self.ledger.finish_attempt(
            attempt["id"],
            status="failed",
            output=envelope,
            error=error,
        )
        self.ledger.finish_invocation(
            invocation["id"],
            status="failed",
            output=envelope,
            error=error,
        )

    def _schedule_retry(
        self,
        run_id: str,
        scope_id: str,
        node_id: str,
        definition: dict[str, Any],
        invocation: dict[str, Any],
        attempt: dict[str, Any],
        error: dict[str, Any],
    ) -> bool:
        retry = definition["retry"]
        retryable_codes = retry.get("retryableCodes", [])
        max_attempts = int(retry.get("maxAttempts", 1))
        if error.get("code") not in retryable_codes or attempt["attempt_no"] >= max_attempts:
            return False
        delay = min(
            float(retry.get("initialDelaySeconds", 2))
            * float(retry.get("backoffMultiplier", 2))
            ** (attempt["attempt_no"] - 1),
            float(retry.get("maxDelaySeconds", 30)),
        )
        next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
        self.ledger.schedule_retry(
            attempt["id"],
            current_node_id=node_id,
            next_attempt_at=_timestamp(next_attempt_at),
            error=error,
            delay_seconds=delay,
        )
        return True

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
                current_scope_id=scope_id,
                current_node_id=node_id,
                current_invocation_id=None,
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
        *,
        route_on_error: bool = True,
    ) -> dict[str, Any]:
        scope = self.ledger.get_scope(scope_id)
        if scope is None:
            raise RunError("execution scope is missing")
        run = self.ledger.get_run(run_id)
        if run is None:
            raise RunError("run not found")
        plan = self._frozen_plan(run, scope["workflow_id"])
        node = plan.nodes.get(node_id)
        error_target = (
            node["definition"].get("onError")
            if node is not None and route_on_error
            else None
        )
        if (
            error_target is not None
            and scope["status"] == "active"
            and run["control_mode"] != "cancel"
        ):
            self.ledger.record_event(
                run_id,
                "error.routed",
                {
                    "from": node_id,
                    "to": error_target,
                    "error": error_output(error)["error"],
                },
                scope_id=scope_id,
            )
            if run["control_mode"] == "pause":
                return self.ledger.update_run(
                    run_id,
                    status="paused",
                    control_mode="pause",
                    current_scope_id=scope_id,
                    current_node_id=error_target,
                    current_invocation_id=None,
                )
            self.ledger.update_run(
                run_id,
                status="running",
                current_scope_id=scope_id,
                current_node_id=error_target,
                current_invocation_id=None,
            )
            return self._drive(run_id, scope_id, error_target)
        if scope["status"] == "active":
            scope = self.ledger.finish_scope(scope_id, status="failed", error=error)
        if scope["parent_invocation_id"] is None:
            return self.ledger.update_run(
                run_id,
                status="failed",
                current_scope_id=scope_id,
                current_node_id=node_id,
                current_invocation_id=None,
                error=error,
            )
        parent_invocation = self.ledger.get_invocation(scope["parent_invocation_id"])
        if parent_invocation is None:
            raise RunError("parent invocation is missing")
        if parent_invocation["status"] in {"planned", "ready", "running", "waiting"}:
            envelope = error_output(error)
            self.ledger.finish_invocation(
                parent_invocation["id"],
                status="failed",
                output=envelope,
                error=error,
            )
        return self._fail_scope(
            run_id,
            parent_invocation["scope_id"],
            parent_invocation["node_id"],
            error,
            route_on_error=route_on_error,
        )

    def _cancel_scope(
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
            self.ledger.finish_scope(scope_id, status="cancelled", error=error)
        if scope["parent_invocation_id"] is None:
            return self.ledger.update_run(
                run_id,
                status="cancelled",
                control_mode="cancel",
                current_scope_id=scope_id,
                current_node_id=node_id,
                current_invocation_id=None,
                error=error,
            )
        parent_invocation = self.ledger.get_invocation(scope["parent_invocation_id"])
        if parent_invocation is None:
            raise RunError("parent invocation is missing")
        if parent_invocation["status"] in {"planned", "ready", "running", "waiting"}:
            self.ledger.finish_invocation(
                parent_invocation["id"],
                status="cancelled",
                error=error,
            )
        return self._cancel_scope(
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
            if (
                invocation["status"] in {"succeeded", "failed"}
                and invocation["output_json"] is not None
            ):
                outputs[invocation["node_id"]] = json.loads(invocation["output_json"])
        return outputs

    def _active_scope_for_node(self, run_id: str, node_id: str) -> dict[str, Any]:
        run = self.ledger.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        scope_id = run["current_scope_id"]
        if scope_id is None:
            raise RunError("run has no persisted continuation scope")
        if run["current_node_id"] != node_id:
            raise RunError("run continuation node does not match requested node")
        scope = self.ledger.get_scope(scope_id)
        if scope is None:
            raise RunError("run continuation scope is missing")
        if scope["status"] != "active":
            raise RunError("run continuation scope is not active")
        if node_id not in self._frozen_plan(run, scope["workflow_id"]).nodes:
            raise RunError(f"node is not in the persisted continuation scope: {node_id}")
        return scope

    def _continuation(self, run: dict[str, Any]) -> tuple[str, str, str | None]:
        scope_id = run["current_scope_id"]
        node_id = run["current_node_id"]
        if scope_id is None or node_id is None:
            raise RunError("run has no persisted continuation")
        invocation_id = run["current_invocation_id"]
        if invocation_id is not None:
            invocation = self.ledger.get_invocation(invocation_id)
            if (
                invocation is None
                or invocation["run_id"] != run["id"]
                or invocation["scope_id"] != scope_id
                or invocation["node_id"] != node_id
            ):
                raise RunError("run has an invalid persisted continuation invocation")
            current = self.ledger.get_invocation_for_node(scope_id, node_id)
            if current is None or current["id"] != invocation_id:
                raise RunError("run has an ambiguous persisted continuation invocation")
        return scope_id, node_id, invocation_id

    def _plan(self, workflow_id: str) -> ExecutionPlan:
        try:
            return self._plans[workflow_id]
        except KeyError as exc:
            raise RunError(f"workflow not found: {workflow_id}") from exc

    def _frozen_plan(self, run: dict[str, Any], workflow_id: str) -> ExecutionPlan:
        try:
            persisted = json.loads(run["plan_json"])
            raw = persisted["workflows"][workflow_id]
            return ExecutionPlan(
                plan_version=raw["planVersion"],
                package_digest=raw["packageDigest"],
                binding_digest=raw.get("bindingDigest"),
                workflow_id=raw["workflowId"],
                defaults=raw["defaults"],
                input_schema_digest=raw["inputSchemaDigest"],
                output_schema_digest=raw["outputSchemaDigest"],
                nodes=raw["nodes"],
                edges=raw["edges"],
                source_map=raw["sourceMap"],
                required_features=raw["requiredFeatures"],
                compiled_plan_digest=raw["compiledPlanDigest"],
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RunError(
                f"persisted execution plan is invalid for workflow: {workflow_id}"
            ) from exc

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
            raise SchemaValidationError(
                f"schema validation failed: {relative_path}: {exc.message}"
            ) from exc

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


def _schema_digest(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(canonical)

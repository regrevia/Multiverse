from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Literal

from multiverse_workflow.runtime.ledger import LedgerConflict
from multiverse_workflow.runtime.projection import build_run_projection
from multiverse_workflow.runtime.runner import RunError, Runner

from .contracts import (
    CommandReceipt,
    HumanDecisionRequest,
    RunControlRequest,
    RunCreateRequest,
)
from .errors import ServiceError, idempotency_conflict, not_found, state_conflict


class RuntimeApplication:
    """Application facade over one configured local Runner and Ledger."""

    def __init__(
        self,
        *,
        package_dir: Path,
        binding_path: Path,
        database_path: Path,
        deployment_id: str = "deployment_local",
        namespace: str = "local",
        subject: str = "local-user",
    ) -> None:
        self.package_dir = package_dir.expanduser().resolve()
        self.binding_path = binding_path.expanduser().resolve()
        self.deployment_id = deployment_id
        self.namespace = namespace
        self.subject = subject
        self.runner = Runner(
            self.package_dir,
            binding_path=self.binding_path,
            database_path=database_path,
            deployment_id=deployment_id,
            namespace=namespace,
        )
    def create_run(
        self,
        request: RunCreateRequest,
        *,
        idempotency_key: str,
    ) -> CommandReceipt:
        self._require_deployment(request.deployment_id)
        self._require_idempotency_key(idempotency_key)
        fingerprint = self._fingerprint(request)
        previous = self._existing_command(idempotency_key, fingerprint, self.namespace)
        if previous is not None and previous["status"] == "completed":
            return self._receipt_from_command(previous)
        if previous is not None and previous["status"] == "rejected":
            return self._receipt_from_command(previous)
        if previous is None:
            run_id = self._new_resource_id("run")
            command_id = self._new_resource_id("cmd")
            try:
                self.runner.ledger.create_command(
                    command_id=command_id,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    operation="run.create",
                    namespace=self.namespace,
                    resource_id=run_id,
                )
            except Exception as exc:
                existing = self._existing_command(idempotency_key, fingerprint, self.namespace)
                if existing is not None:
                    return self._receipt_from_command(existing)
                raise ServiceError("COMMAND_REJECTED", str(exc), status_code=409) from exc
        else:
            command_id = str(previous["id"])
            run_id = str(previous["resource_id"])

        existing_run = self.runner.ledger.get_run(run_id)
        if existing_run is not None:
            self.runner.ledger.finish_command(
                command_id,
                status="completed",
                resource_version=int(existing_run["version"]),
            )
            return self._receipt(
                "run.create",
                existing_run,
                request_id=command_id,
                status="completed",
            )

        try:
            run = self.runner.start(
                request.input,
                workflow_id=request.workflow_id,
                run_id=run_id,
            )
        except (KeyError, RunError, LedgerConflict) as exc:
            self.runner.ledger.finish_command(
                command_id,
                status="rejected",
                error={"message": str(exc)},
            )
            raise ServiceError("RUN_REJECTED", str(exc), status_code=422) from exc
        self.runner.ledger.finish_command(
            command_id,
            status="completed",
            resource_version=int(run["version"]),
        )
        return self._receipt("run.create", run, request_id=command_id, status="completed")

    def get_command(self, namespace: str, command_id: str) -> dict[str, Any]:
        self._require_namespace(namespace)
        command = self.runner.ledger.get_command(command_id)
        if command is None or command["namespace"] != namespace:
            raise not_found(f"command not found: {command_id}")
        return {
            "request_id": command["id"],
            "status": command["status"],
            "resource_id": command["resource_id"],
            "operation": command["operation"],
            "resource_version": command["resource_version"],
            "created_at": command["created_at"],
            "updated_at": command["updated_at"],
        }

    def get_run(self, namespace: str, run_id: str) -> dict[str, Any]:
        run = self._require_run(namespace, run_id)
        return run

    def get_graph(self, namespace: str, run_id: str) -> dict[str, Any]:
        self._require_run(namespace, run_id)
        return build_run_projection(self.runner.ledger, run_id)

    def list_events(
        self,
        namespace: str,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_run(namespace, run_id)
        try:
            return self.runner.ledger.list_events_after(
                run_id,
                after_seq=after,
                limit=limit,
            )
        except ValueError as exc:
            raise ServiceError("INVALID_ARGUMENT", str(exc), status_code=422) from exc

    def event_cursor(self, namespace: str, run_id: str) -> int:
        self._require_run(namespace, run_id)
        return self.runner.ledger.get_event_cursor(run_id)

    def control_run(
        self,
        namespace: str,
        run_id: str,
        operation: Literal["pause", "resume", "cancel"],
        request: RunControlRequest,
        *,
        idempotency_key: str,
    ) -> CommandReceipt:
        self._require_run(namespace, run_id)
        self._require_idempotency_key(idempotency_key)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "namespace": namespace,
                    "runId": run_id,
                    "operation": operation,
                    "request": request.model_dump(mode="json", by_alias=True),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        previous = self._existing_command(idempotency_key, fingerprint, namespace)
        if previous is not None:
            return self._receipt_from_command(previous)
        command_id = self._new_resource_id("cmd")
        resource_id = run_id
        self.runner.ledger.create_command(
            command_id=command_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            operation=f"run.{operation}",
            namespace=namespace,
            resource_id=resource_id,
        )
        try:
            if operation == "resume":
                run = self.runner.resume(
                    run_id,
                    expected_version=request.expected_version,
                    reason=request.reason,
                )
            elif operation == "pause":
                run = self.runner.pause(
                    run_id,
                    expected_version=request.expected_version,
                    reason=request.reason,
                )
            else:
                run = self.runner.cancel(
                    run_id,
                    expected_version=request.expected_version,
                    reason=request.reason,
                )
        except (KeyError, LedgerConflict, RunError) as exc:
            self.runner.ledger.finish_command(
                command_id,
                status="rejected",
                error={"message": str(exc)},
            )
            raise state_conflict(str(exc)) from exc
        self.runner.ledger.finish_command(
            command_id,
            status="completed",
            resource_version=int(run["version"]),
        )
        return self._receipt(
            f"run.{operation}",
            run,
            request_id=command_id,
            status="completed",
        )

    def list_human_requests(
        self,
        namespace: str,
        *,
        run_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if run_id is not None:
            self._require_run(namespace, run_id)
        else:
            self._require_namespace(namespace)
        requests = self.runner.ledger.list_human_requests(run_id=run_id, status=status)
        return [
            request
            for request in requests
            if request["run_id"] and self._run_namespace(request["run_id"]) == namespace
        ]

    def decide_human_request(
        self,
        namespace: str,
        request_id: str,
        request: HumanDecisionRequest,
        *,
        idempotency_key: str,
    ) -> CommandReceipt:
        human_request = self.runner.ledger.get_human_request(request_id)
        if human_request is None:
            raise not_found(f"human request not found: {request_id}")
        run = self._require_run(namespace, human_request["run_id"])
        self._require_idempotency_key(idempotency_key)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "namespace": namespace,
                    "requestId": request_id,
                    "request": request.model_dump(mode="json", by_alias=True),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        previous = self._existing_command(idempotency_key, fingerprint, namespace)
        if previous is not None:
            return self._receipt_from_command(previous)
        command_id = self._new_resource_id("cmd")
        self.runner.ledger.create_command(
            command_id=command_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            operation="human-request.decide",
            namespace=namespace,
            resource_id=run["id"],
        )
        try:
            finished = self.runner.decide(
                request_id,
                choice=request.choice,
                decision=request.decision,
                comment=request.comment,
                actor=self.subject,
                subject_digest=request.subject_digest,
                expected_version=request.expected_version,
                idempotency_key=idempotency_key,
            )
        except (KeyError, LedgerConflict, RunError) as exc:
            self.runner.ledger.finish_command(
                command_id,
                status="rejected",
                error={"message": str(exc)},
            )
            raise state_conflict(str(exc)) from exc
        self.runner.ledger.finish_command(
            command_id,
            status="completed",
            resource_version=int(finished["version"]),
        )
        return self._receipt(
            "human-request.decide",
            finished,
            request_id=command_id,
            status="completed",
            fallback=run,
        )

    def close(self) -> None:
        self.runner.ledger.close()

    def _require_run(self, namespace: str, run_id: str) -> dict[str, Any]:
        self._require_namespace(namespace)
        run = self.runner.ledger.get_run(run_id)
        if run is None:
            raise not_found(f"run not found: {run_id}")
        if run["namespace"] != namespace:
            raise not_found(f"run not found: {run_id}")
        return run

    def _run_namespace(self, run_id: str) -> str:
        run = self.runner.ledger.get_run(run_id)
        return "" if run is None else str(run["namespace"])

    def _require_namespace(self, namespace: str) -> None:
        if namespace != self.namespace:
            raise not_found(f"namespace not found: {namespace}")

    def _require_deployment(self, deployment_id: str) -> None:
        if deployment_id != self.deployment_id:
            raise ServiceError(
                "DATA_REFERENCE_MISSING",
                f"deployment is not available: {deployment_id}",
                status_code=422,
            )

    @staticmethod
    def _require_idempotency_key(key: str) -> None:
        if not key.strip():
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key must not be empty",
                status_code=422,
            )

    def _existing_command(
        self,
        idempotency_key: str,
        fingerprint: str,
        namespace: str,
    ) -> dict[str, Any] | None:
        command = self.runner.ledger.get_command_by_key(idempotency_key)
        if command is None:
            return None
        if command["namespace"] != namespace or command["fingerprint"] != fingerprint:
            raise idempotency_conflict("idempotency key was already used for another request")
        return command

    @staticmethod
    def _new_resource_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _receipt_from_command(self, command: dict[str, Any]) -> CommandReceipt:
        if command["status"] == "rejected":
            error = json.loads(command["error_json"] or "{}")
            raise ServiceError(
                "RUN_REJECTED",
                str(error.get("message", "command was rejected")),
                status_code=422,
            )
        return CommandReceipt(
            requestId=command["id"],
            status=command["status"],
            resourceId=command["resource_id"],
            operation=command["operation"],
            resourceVersion=command["resource_version"],
        )

    @staticmethod
    def _fingerprint(request: RunCreateRequest) -> str:
        payload = request.model_dump(mode="json", by_alias=True)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _receipt(
        operation: str,
        run: dict[str, Any],
        *,
        status: Literal["accepted", "completed"] = "accepted",
        fallback: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> CommandReceipt:
        source = run or fallback
        if source is None:
            raise ServiceError("RUN_REJECTED", "runtime returned no run record", status_code=500)
        return CommandReceipt(
            requestId=request_id or f"req_{uuid.uuid4().hex}",
            status=status,
            resourceId=str(source["id"]),
            operation=operation,
            resourceVersion=int(source["version"]),
        )

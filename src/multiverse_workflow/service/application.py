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
from .errors import ServiceError, not_found, state_conflict


class RuntimeApplication:
    """Application facade over one configured local Runner and Ledger."""

    def __init__(
        self,
        *,
        package_dir: Path,
        binding_path: Path,
        database_path: Path,
        namespace: str = "local",
    ) -> None:
        self.package_dir = package_dir.expanduser().resolve()
        self.binding_path = binding_path.expanduser().resolve()
        self.namespace = namespace
        self.runner = Runner(
            self.package_dir,
            binding_path=self.binding_path,
            database_path=database_path,
            namespace=namespace,
        )
        self._idempotency: dict[str, tuple[str, CommandReceipt]] = {}

    def create_run(
        self,
        request: RunCreateRequest,
        *,
        idempotency_key: str,
    ) -> CommandReceipt:
        self._require_namespace(request.namespace)
        self._require_deployment(request)
        self._require_idempotency_key(idempotency_key)
        fingerprint = self._fingerprint(request)
        previous = self._idempotency.get(idempotency_key)
        if previous is not None:
            if previous[0] != fingerprint:
                raise state_conflict("idempotency key was already used for another request")
            return previous[1]

        try:
            run = self.runner.start(request.input, workflow_id=request.workflow)
        except (KeyError, RunError, LedgerConflict) as exc:
            raise ServiceError("RUN_REJECTED", str(exc), status_code=422) from exc
        receipt = self._receipt("run.create", run)
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        return receipt

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
    ) -> CommandReceipt:
        self._require_run(namespace, run_id)
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
            raise state_conflict(str(exc)) from exc
        return self._receipt(f"run.{operation}", run, status="completed")

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
        try:
            finished = self.runner.decide(
                request_id,
                choice=request.choice,
                decision=request.decision,
                comment=request.comment,
                actor=request.actor,
                subject_digest=request.subject_digest,
                expected_version=request.expected_version,
                idempotency_key=idempotency_key,
            )
        except (KeyError, LedgerConflict, RunError) as exc:
            raise state_conflict(str(exc)) from exc
        return self._receipt("human-request.decide", finished, status="completed", fallback=run)

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

    def _require_deployment(self, request: RunCreateRequest) -> None:
        requested_package = Path(request.package).expanduser().resolve()
        requested_binding = Path(request.binding).expanduser().resolve()
        if requested_package != self.package_dir or requested_binding != self.binding_path:
            raise ServiceError(
                "DEPLOYMENT_MISMATCH",
                "request package and binding do not match the configured local deployment",
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
    ) -> CommandReceipt:
        source = run or fallback
        if source is None:
            raise ServiceError("RUN_REJECTED", "runtime returned no run record", status_code=500)
        return CommandReceipt(
            requestId=f"req_{uuid.uuid4().hex}",
            status=status,
            resourceId=str(source["id"]),
            operation=operation,
            resourceVersion=int(source["version"]),
        )

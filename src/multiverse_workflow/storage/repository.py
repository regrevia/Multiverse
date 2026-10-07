from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from multiverse_workflow.runtime.http_job import validate_artifact_metadata
from multiverse_workflow.storage.sqlalchemy import PostgresTransactionStore


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


_UNSET = object()


class PostgresLedgerRepository:
    """PostgreSQL persistence slice for queued Run creation and inspection.

    It intentionally does not replace the SQLite Ledger yet. The shared
    business repository contract will be introduced after this transaction
    slice has parity tests.
    """

    def __init__(self, dsn: str) -> None:
        self._store = PostgresTransactionStore(dsn)

    def create_queued_run(
        self,
        *,
        namespace: str,
        deployment_id: str | None,
        workflow_id: str,
        package_digest: str,
        binding_digest: str | None,
        plan: dict[str, Any],
        input_value: Any,
        deadline_at: str,
        entry_node_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if not namespace.strip() or not workflow_id.strip() or not entry_node_id.strip():
            raise ValueError("namespace, workflow_id and entry_node_id are required")
        run_id = run_id or _new_id("run")
        scope_id = _new_id("scope")
        wait_id = _new_id("wait")
        now = _now()
        input_json = _json(input_value)
        input_digest = _digest(input_json)
        plan_json = _json(plan)
        with self._store.transaction() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        id, namespace, deployment_id, workflow_id, package_digest,
                        binding_digest, plan_json, input_json, input_digest, status,
                        control_mode, deadline_at, version, current_node_id,
                        rerun_of, rerun_reason, created_at, updated_at
                    ) VALUES (
                        :run_id, :namespace, :deployment_id, :workflow_id,
                        :package_digest, :binding_digest, :plan_json, :input_json,
                        :input_digest, 'queued', 'run', :deadline_at, 1,
                        :entry_node_id, NULL, NULL, :now, :now
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "namespace": namespace,
                    "deployment_id": deployment_id,
                    "workflow_id": workflow_id,
                    "package_digest": package_digest,
                    "binding_digest": binding_digest,
                    "plan_json": plan_json,
                    "input_json": input_json,
                    "input_digest": input_digest,
                    "deadline_at": deadline_at,
                    "entry_node_id": entry_node_id,
                    "now": now,
                },
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=1,
                event_type="run.created",
                payload={"status": "queued", "workflowId": workflow_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO scopes (
                        id, run_id, workflow_id, path_json, input_json,
                        input_digest, status, created_at
                    ) VALUES (
                        :scope_id, :run_id, :workflow_id, :path_json,
                        :input_json, :input_digest, 'active', :now
                    )
                    """
                ),
                {
                    "scope_id": scope_id,
                    "run_id": run_id,
                    "workflow_id": workflow_id,
                    "path_json": _json(["root"]),
                    "input_json": input_json,
                    "input_digest": input_digest,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE runs
                    SET current_scope_id = :scope_id, updated_at = :now
                    WHERE id = :run_id
                    """
                ),
                {"scope_id": scope_id, "now": now, "run_id": run_id},
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=2,
                event_type="scope.created",
                payload={
                    "scopeId": scope_id,
                    "workflowId": workflow_id,
                    "inputDigest": input_digest,
                },
                scope_id=scope_id,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id,
                        not_before, payload_json, status, created_at, updated_at
                    ) VALUES (
                        :wait_id, :namespace, :wait_key, 'run-start',
                        :run_id, :scope_id, :now, :payload_json, 'pending',
                        :now, :now
                    )
                    """
                ),
                {
                    "wait_id": wait_id,
                    "namespace": namespace,
                    "wait_key": f"run-start:{run_id}",
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "now": now,
                    "payload_json": _json({"runId": run_id, "scopeId": scope_id}),
                },
            )
        loaded = self.get_run(namespace, run_id)
        if loaded is None:
            raise RuntimeError("queued run disappeared after commit")
        return loaded

    def get_run(self, namespace: str, run_id: str) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text("SELECT * FROM runs WHERE id = :run_id AND namespace = :namespace"),
                {"run_id": run_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def update_run(
        self,
        *,
        namespace: str,
        run_id: str,
        expected_version: int,
        status: str,
        control_mode: str,
        current_node_id: str | None,
        current_scope_id: str | None | object = _UNSET,
        current_invocation_id: str | None | object = _UNSET,
        output: Any = None,
        error: Any = None,
        next_attempt_at: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        with self._store.transaction() as connection:
            run = connection.execute(
                text(
                    "SELECT * FROM runs "
                    "WHERE id = :run_id AND namespace = :namespace "
                    "FOR UPDATE"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).mappings().first()
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            if int(run["version"]) != expected_version:
                raise ValueError("run version conflict")
            scope_id = (
                run["current_scope_id"]
                if current_scope_id is _UNSET
                else current_scope_id
            )
            invocation_id = (
                run["current_invocation_id"]
                if current_invocation_id is _UNSET
                else current_invocation_id
            )
            if (
                current_invocation_id is _UNSET
                and (
                    current_node_id != run["current_node_id"]
                    or scope_id != run["current_scope_id"]
                )
            ):
                invocation_id = None
            next_attempt = (
                run["next_attempt_at"]
                if next_attempt_at is _UNSET
                else next_attempt_at
            )
            if scope_id is not None:
                scope = connection.execute(
                    text("SELECT run_id FROM scopes WHERE id = :scope_id"),
                    {"scope_id": scope_id},
                ).mappings().first()
                if scope is None or scope["run_id"] != run_id:
                    raise ValueError("continuation scope does not belong to run")
            if invocation_id is not None:
                invocation = connection.execute(
                    text(
                        "SELECT run_id, scope_id, node_id FROM invocations "
                        "WHERE id = :invocation_id"
                    ),
                    {"invocation_id": invocation_id},
                ).mappings().first()
                if invocation is None or invocation["run_id"] != run_id:
                    raise ValueError("continuation invocation does not belong to run")
                if invocation["scope_id"] != scope_id:
                    raise ValueError("continuation invocation does not belong to scope")
                if invocation["node_id"] != current_node_id:
                    raise ValueError("continuation invocation node does not match")
            version = expected_version + 1
            connection.execute(
                text(
                    """
                    UPDATE runs
                    SET status = :status, control_mode = :control_mode,
                        current_node_id = :current_node_id,
                        current_scope_id = :current_scope_id,
                        current_invocation_id = :current_invocation_id,
                        output_json = :output_json, error_json = :error_json,
                        next_attempt_at = :next_attempt_at, version = :version,
                        updated_at = :now
                    WHERE id = :run_id AND namespace = :namespace
                      AND version = :expected_version
                    """
                ),
                {
                    "status": status,
                    "control_mode": control_mode,
                    "current_node_id": current_node_id,
                    "current_scope_id": scope_id,
                    "current_invocation_id": invocation_id,
                    "output_json": _json(output) if output is not None else None,
                    "error_json": _json(error) if error is not None else None,
                    "next_attempt_at": next_attempt,
                    "version": version,
                    "now": _now(),
                    "run_id": run_id,
                    "namespace": namespace,
                    "expected_version": expected_version,
                },
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=self._next_event_sequence(connection, run_id),
                event_type="run.updated",
                payload={
                    "status": status,
                    "controlMode": control_mode,
                    "currentNodeId": current_node_id,
                    "currentScopeId": scope_id,
                    "currentInvocationId": invocation_id,
                    "version": version,
                },
                scope_id=scope_id if isinstance(scope_id, str) else None,
                invocation_id=(
                    invocation_id if isinstance(invocation_id, str) else None
                ),
            )
        updated = self.get_run(namespace, run_id)
        if updated is None:
            raise RuntimeError("run disappeared after update")
        return updated

    def control_run(
        self,
        *,
        namespace: str,
        run_id: str,
        operation: str,
        expected_version: int,
        reason: str,
    ) -> dict[str, Any]:
        if operation not in {"pause", "resume", "cancel"}:
            raise ValueError("unsupported run control operation")
        if not reason.strip():
            raise ValueError("control reason must not be empty")
        with self._store.transaction() as connection:
            run = connection.execute(
                text(
                    "SELECT * FROM runs "
                    "WHERE id = :run_id AND namespace = :namespace "
                    "FOR UPDATE"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).mappings().first()
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            if int(run["version"]) != expected_version:
                raise ValueError("run version conflict")
            if operation == "pause":
                if run["status"] not in {"queued", "running", "waiting"}:
                    raise ValueError(f"run cannot be paused from status: {run['status']}")
                status, control_mode, event_type = "paused", "pause", "run.paused"
            elif operation == "resume":
                if run["status"] != "paused" or run["control_mode"] != "pause":
                    raise ValueError("only a paused run can resume")
                status, control_mode, event_type = "running", "run", "run.resumed"
            else:
                if run["status"] in {"succeeded", "failed", "cancelled"}:
                    raise ValueError("run is already terminal")
                active = connection.execute(
                    text(
                        "SELECT 1 FROM attempts WHERE run_id = :run_id "
                        "AND status IN ('created', 'submitted', 'running', 'unknown') "
                        "LIMIT 1"
                    ),
                    {"run_id": run_id},
                ).first()
                connection.execute(
                    text(
                        "UPDATE human_requests SET status = 'cancelled', "
                        "version = version + 1, updated_at = :now "
                        "WHERE run_id = :run_id AND status = 'pending'"
                    ),
                    {"run_id": run_id, "now": _now()},
                )
                connection.execute(
                    text(
                        "UPDATE waits SET status = 'cancelled', updated_at = :now "
                        "WHERE run_id = :run_id AND status IN ('pending', 'claimed')"
                    ),
                    {"run_id": run_id, "now": _now()},
                )
                if active is None:
                    cancellation_error = _json(
                        {"code": "RUN_CANCELLED", "message": reason}
                    )
                    connection.execute(
                        text(
                            """
                            UPDATE attempts
                            SET status = 'cancelled', error_json = :error_json,
                                updated_at = :now
                            WHERE run_id = :run_id
                              AND status IN ('created', 'waiting')
                            """
                        ),
                        {
                            "error_json": cancellation_error,
                            "now": _now(),
                            "run_id": run_id,
                        },
                    )
                    connection.execute(
                        text(
                            """
                            UPDATE invocations
                            SET status = 'cancelled', error_json = :error_json,
                                version = version + 1, updated_at = :now
                            WHERE run_id = :run_id
                              AND status IN ('planned', 'running', 'waiting')
                            """
                        ),
                        {
                            "error_json": cancellation_error,
                            "now": _now(),
                            "run_id": run_id,
                        },
                    )
                    connection.execute(
                        text(
                            """
                            UPDATE scopes
                            SET status = 'cancelled', error_json = :error_json
                            WHERE run_id = :run_id AND status = 'active'
                            """
                        ),
                        {"error_json": cancellation_error, "run_id": run_id},
                    )
                status = "stopping" if active is not None else "cancelled"
                control_mode, event_type = "cancel", (
                    "run.cancel_requested" if active is not None else "run.cancelled"
                )
            version = int(run["version"]) + 1
            connection.execute(
                text(
                    """
                    UPDATE runs
                    SET status = :status, control_mode = :control_mode,
                        version = :version, updated_at = :now,
                        next_attempt_at = CASE
                            WHEN :operation = 'cancel' THEN NULL
                            ELSE next_attempt_at
                        END
                    WHERE id = :run_id AND namespace = :namespace
                      AND version = :expected_version
                    """
                ),
                {
                    "status": status,
                    "control_mode": control_mode,
                    "version": version,
                    "now": _now(),
                    "operation": operation,
                    "run_id": run_id,
                    "namespace": namespace,
                    "expected_version": expected_version,
                },
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=self._next_event_sequence(connection, run_id),
                event_type=event_type,
                payload={
                    "operation": operation,
                    "reason": reason,
                    "status": status,
                    "controlMode": control_mode,
                    "version": version,
                },
            )
        updated = self.get_run(namespace, run_id)
        if updated is None:
            raise RuntimeError("run disappeared after control")
        return updated

    def create_command(
        self,
        *,
        namespace: str,
        subject: str,
        operation: str,
        idempotency_key: str,
        fingerprint: str,
        resource_id: str,
        command_id: str,
    ) -> dict[str, Any]:
        for value, name in (
            (namespace, "namespace"),
            (subject, "subject"),
            (operation, "operation"),
            (idempotency_key, "idempotency key"),
            (fingerprint, "fingerprint"),
            (resource_id, "resource id"),
            (command_id, "command id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        now = _now()
        with self._store.transaction() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO commands (
                        id, idempotency_key, fingerprint, operation, namespace,
                        subject, resource_id, status, resource_version,
                        before_version, after_version, transition, error_json,
                        created_at, updated_at
                    ) VALUES (
                        :command_id, :idempotency_key, :fingerprint, :operation,
                        :namespace, :subject, :resource_id, 'accepted', NULL,
                        NULL, NULL, NULL, NULL, :now, :now
                    )
                    """
                ),
                {
                    "command_id": command_id,
                    "idempotency_key": idempotency_key,
                    "fingerprint": fingerprint,
                    "operation": operation,
                    "namespace": namespace,
                    "subject": subject,
                    "resource_id": resource_id,
                    "now": now,
                },
            )
        created = self.get_command(namespace, command_id)
        if created is None:
            raise RuntimeError("command disappeared after commit")
        return created

    def get_command(self, namespace: str, command_id: str) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM commands "
                    "WHERE id = :command_id AND namespace = :namespace"
                ),
                {"command_id": command_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_command_by_key(
        self,
        *,
        namespace: str,
        subject: str,
        operation: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT * FROM commands
                    WHERE namespace = :namespace AND subject = :subject
                      AND operation = :operation
                      AND idempotency_key = :idempotency_key
                    """
                ),
                {
                    "namespace": namespace,
                    "subject": subject,
                    "operation": operation,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
        return dict(row) if row is not None else None

    def list_commands_by_key(
        self,
        *,
        namespace: str,
        idempotency_key: str,
    ) -> list[dict[str, Any]]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT * FROM commands
                    WHERE namespace = :namespace
                      AND idempotency_key = :idempotency_key
                    ORDER BY created_at, id
                    """
                ),
                {"namespace": namespace, "idempotency_key": idempotency_key},
            ).mappings().all()
        return [dict(row) for row in rows]

    def finish_command(
        self,
        *,
        namespace: str,
        command_id: str,
        status: str,
        resource_version: int | None = None,
        error: Any = None,
    ) -> dict[str, Any]:
        if status not in {"completed", "rejected"}:
            raise ValueError("command status must be completed or rejected")
        with self._store.transaction() as connection:
            existing = connection.execute(
                text(
                    "SELECT * FROM commands "
                    "WHERE id = :command_id AND namespace = :namespace "
                    "FOR UPDATE"
                ),
                {"command_id": command_id, "namespace": namespace},
            ).mappings().first()
            if existing is None:
                raise KeyError(f"command not found: {command_id}")
            error_json = _json(error) if error is not None else None
            if existing["status"] != "accepted":
                if (
                    existing["status"] == status
                    and existing["resource_version"] == resource_version
                    and existing["error_json"] == error_json
                ):
                    return dict(existing)
                raise IntegrityError(
                    "command terminal state conflict",
                    params=None,
                    orig=ValueError("command terminal state conflict"),
                )
            connection.execute(
                text(
                    """
                    UPDATE commands
                    SET status = :status, resource_version = :resource_version,
                        error_json = :error_json, updated_at = :now
                    WHERE id = :command_id AND namespace = :namespace
                    """
                ),
                {
                    "status": status,
                    "resource_version": resource_version,
                    "error_json": error_json,
                    "now": _now(),
                    "command_id": command_id,
                    "namespace": namespace,
                },
            )
        completed = self.get_command(namespace, command_id)
        if completed is None:
            raise RuntimeError("command disappeared after update")
        return completed

    def list_queued_runs(
        self,
        *,
        namespace: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not namespace.strip():
            raise ValueError("namespace is required")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT * FROM runs
                    WHERE namespace = :namespace AND status = 'queued'
                    ORDER BY created_at, id
                    LIMIT :limit
                    """
                ),
                {"namespace": namespace, "limit": limit},
            ).mappings().all()
        return [dict(row) for row in rows]

    def list_run_events(self, namespace: str, run_id: str) -> list[str]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT events.type FROM run_events events "
                    "JOIN runs ON runs.id = events.run_id "
                    "WHERE events.run_id = :run_id AND runs.namespace = :namespace "
                    "ORDER BY events.seq"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).all()
        return [str(row[0]) for row in rows]

    def list_waits(self, namespace: str, run_id: str) -> list[str]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT wait_key FROM waits "
                    "WHERE run_id = :run_id AND namespace = :namespace "
                    "ORDER BY created_at"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).all()
        return [str(row[0]) for row in rows]

    def get_wait_by_key(
        self,
        *,
        namespace: str,
        wait_key: str,
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM waits "
                    "WHERE namespace = :namespace AND wait_key = :wait_key"
                ),
                {"namespace": namespace, "wait_key": wait_key},
            ).mappings().first()
        return dict(row) if row is not None else None

    def list_wait_records(
        self,
        *,
        namespace: str,
        run_id: str | None = None,
        kind: str | None = None,
        statuses: tuple[str, ...] = ("pending", "claimed"),
    ) -> list[dict[str, Any]]:
        if not namespace.strip():
            raise ValueError("namespace is required")
        if not statuses:
            return []
        conditions = ["namespace = :namespace", "status = ANY(:statuses)"]
        parameters: dict[str, Any] = {
            "namespace": namespace,
            "statuses": list(statuses),
        }
        if run_id is not None:
            conditions.append("run_id = :run_id")
            parameters["run_id"] = run_id
        if kind is not None:
            conditions.append("kind = :kind")
            parameters["kind"] = kind
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM waits WHERE "
                    + " AND ".join(conditions)
                    + " ORDER BY not_before, created_at, id"
                ),
                parameters,
            ).mappings().all()
        return [dict(row) for row in rows]

    def list_due_wait_records(
        self,
        *,
        namespace: str,
        now: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not namespace.strip():
            raise ValueError("namespace is required")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT * FROM waits
                    WHERE namespace = :namespace
                      AND status = 'pending'
                      AND not_before <= :now
                    ORDER BY not_before, created_at, id
                    LIMIT :limit
                    """
                ),
                {"namespace": namespace, "now": now, "limit": limit},
            ).mappings().all()
        return [dict(row) for row in rows]

    def get_wait(self, *, namespace: str, wait_id: str) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM waits "
                    "WHERE id = :wait_id AND namespace = :namespace"
                ),
                {"wait_id": wait_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def claim_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
        now: str,
    ) -> dict[str, Any] | None:
        if not namespace.strip():
            raise ValueError("namespace is required")
        if not worker_id.strip():
            raise ValueError("worker id is required")
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    UPDATE waits
                    SET status = 'claimed', worker_id = :worker_id,
                        claimed_at = :now, updated_at = :now
                    WHERE id = :wait_id AND namespace = :namespace
                      AND status = 'pending' AND not_before <= :now
                    RETURNING *
                    """
                ),
                {
                    "wait_id": wait_id,
                    "namespace": namespace,
                    "worker_id": worker_id,
                    "now": now,
                },
            ).mappings().first()
        return dict(row) if row is not None else None

    def complete_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        if not worker_id.strip():
            raise ValueError("worker id is required")
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM waits "
                    "WHERE id = :wait_id AND namespace = :namespace"
                ),
                {"wait_id": wait_id, "namespace": namespace},
            ).mappings().first()
            if row is None:
                raise KeyError(f"wait not found: {wait_id}")
            if row["status"] in {"completed", "cancelled"}:
                return dict(row)
            if row["status"] != "claimed":
                raise ValueError(f"wait is not claimed: {row['status']}")
            updated = connection.execute(
                text(
                    """
                    UPDATE waits SET status = 'completed', updated_at = :now
                    WHERE id = :wait_id AND namespace = :namespace
                      AND status = 'claimed' AND worker_id = :worker_id
                    RETURNING *
                    """
                ),
                {
                    "wait_id": wait_id,
                    "namespace": namespace,
                    "worker_id": worker_id,
                    "now": _now(),
                },
            ).mappings().first()
            if updated is None:
                current = connection.execute(
                    text(
                        "SELECT status, worker_id FROM waits "
                        "WHERE id = :wait_id AND namespace = :namespace"
                    ),
                    {"wait_id": wait_id, "namespace": namespace},
                ).mappings().one()
                if current["worker_id"] != worker_id:
                    raise ValueError("wait is claimed by another worker")
                raise ValueError(f"wait state changed: {current['status']}")
        return dict(updated)

    def release_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        if not worker_id.strip():
            raise ValueError("worker id is required")
        with self._store.transaction() as connection:
            updated = connection.execute(
                text(
                    """
                    UPDATE waits
                    SET status = 'pending', worker_id = NULL, claimed_at = NULL,
                        updated_at = :now
                    WHERE id = :wait_id AND namespace = :namespace
                      AND status = 'claimed' AND worker_id = :worker_id
                    RETURNING *
                    """
                ),
                {
                    "wait_id": wait_id,
                    "namespace": namespace,
                    "worker_id": worker_id,
                    "now": _now(),
                },
            ).mappings().first()
            if updated is not None:
                return dict(updated)
            row = connection.execute(
                text(
                    "SELECT * FROM waits "
                    "WHERE id = :wait_id AND namespace = :namespace"
                ),
                {"wait_id": wait_id, "namespace": namespace},
            ).mappings().first()
            if row is None:
                raise KeyError(f"wait not found: {wait_id}")
            if row["worker_id"] != worker_id and row["status"] == "claimed":
                raise ValueError("wait is claimed by another worker")
        return dict(row)

    def reschedule_wait(
        self,
        *,
        namespace: str,
        wait_id: str,
        worker_id: str,
        not_before: str,
    ) -> dict[str, Any]:
        if not worker_id.strip():
            raise ValueError("worker id is required")
        with self._store.transaction() as connection:
            updated = connection.execute(
                text(
                    """
                    UPDATE waits
                    SET status = 'pending', worker_id = NULL, claimed_at = NULL,
                        not_before = :not_before, updated_at = :now
                    WHERE id = :wait_id AND namespace = :namespace
                      AND status = 'claimed' AND worker_id = :worker_id
                    RETURNING *
                    """
                ),
                {
                    "wait_id": wait_id,
                    "namespace": namespace,
                    "worker_id": worker_id,
                    "not_before": not_before,
                    "now": _now(),
                },
            ).mappings().first()
            if updated is not None:
                return dict(updated)
            row = connection.execute(
                text(
                    "SELECT status, worker_id FROM waits "
                    "WHERE id = :wait_id AND namespace = :namespace"
                ),
                {"wait_id": wait_id, "namespace": namespace},
            ).mappings().first()
            if row is None:
                raise KeyError(f"wait not found: {wait_id}")
            if row["status"] == "claimed" and row["worker_id"] != worker_id:
                raise ValueError("wait is claimed by another worker")
            raise ValueError(f"wait cannot be rescheduled from {row['status']}")

    def requeue_stale_waits(
        self,
        *,
        namespace: str,
        older_than: str,
        now: str,
    ) -> int:
        if not namespace.strip():
            raise ValueError("namespace is required")
        with self._store.transaction() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE waits
                    SET status = 'pending', worker_id = NULL, claimed_at = NULL,
                        updated_at = :now
                    WHERE namespace = :namespace
                      AND status = 'claimed'
                      AND claimed_at IS NOT NULL
                      AND claimed_at <= :older_than
                    """
                ),
                {
                    "namespace": namespace,
                    "older_than": older_than,
                    "now": now,
                },
            )
            return int(result.rowcount)

    def list_scope_ids(self, namespace: str, run_id: str) -> list[str]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT scopes.id FROM scopes "
                    "JOIN runs ON runs.id = scopes.run_id "
                    "WHERE scopes.run_id = :run_id AND runs.namespace = :namespace "
                    "ORDER BY scopes.created_at, scopes.id"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).all()
        return [str(row[0]) for row in rows]

    def get_scope(self, namespace: str, scope_id: str) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT scopes.* FROM scopes "
                    "JOIN runs ON runs.id = scopes.run_id "
                    "WHERE scopes.id = :scope_id AND runs.namespace = :namespace"
                ),
                {"scope_id": scope_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_invocation(
        self, namespace: str, invocation_id: str
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT invocations.* FROM invocations "
                    "JOIN runs ON runs.id = invocations.run_id "
                    "WHERE invocations.id = :invocation_id "
                    "AND runs.namespace = :namespace"
                ),
                {"invocation_id": invocation_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_attempt(self, namespace: str, attempt_id: str) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT attempts.* FROM attempts "
                    "JOIN runs ON runs.id = attempts.run_id "
                    "WHERE attempts.id = :attempt_id AND runs.namespace = :namespace"
                ),
                {"attempt_id": attempt_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def list_invocations(self, namespace: str, run_id: str) -> list[str]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT invocations.id FROM invocations "
                    "JOIN runs ON runs.id = invocations.run_id "
                    "WHERE invocations.run_id = :run_id "
                    "AND runs.namespace = :namespace "
                    "ORDER BY invocations.created_at, invocations.id"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).all()
        return [str(row[0]) for row in rows]

    def list_attempts(self, namespace: str, run_id: str) -> list[str]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT attempts.id FROM attempts "
                    "JOIN runs ON runs.id = attempts.run_id "
                    "WHERE attempts.run_id = :run_id "
                    "AND runs.namespace = :namespace "
                    "ORDER BY attempts.created_at, attempts.attempt_no"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).all()
        return [str(row[0]) for row in rows]

    def list_event_records(
        self, namespace: str, run_id: str
    ) -> list[dict[str, Any]]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT events.* FROM run_events events "
                    "JOIN runs ON runs.id = events.run_id "
                    "WHERE events.run_id = :run_id AND runs.namespace = :namespace "
                    "ORDER BY events.seq"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).mappings().all()
        return [dict(row) for row in rows]

    def create_invocation_attempt(
        self,
        *,
        namespace: str,
        run_id: str,
        scope_id: str,
        node_id: str,
        input_value: Any,
        dispatch_key: str,
        effect_key: str,
        attempt_no: int = 1,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if attempt_no < 1:
            raise ValueError("attempt_no must be positive")
        input_json = _json(input_value)
        input_digest = _digest(input_json)
        invocation_id = _new_id("inv")
        attempt_id = _new_id("attempt")
        now = _now()
        with self._store.transaction() as connection:
            scope = connection.execute(
                text(
                    "SELECT id, run_id FROM scopes "
                    "WHERE id = :scope_id AND run_id = :run_id"
                ),
                {"scope_id": scope_id, "run_id": run_id},
            ).mappings().first()
            if scope is None:
                raise IntegrityError(
                    "scope does not belong to run",
                    params=None,
                    orig=ValueError("scope does not belong to run"),
                )
            run = connection.execute(
                text(
                    "SELECT namespace FROM runs WHERE id = :run_id AND namespace = :namespace"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).mappings().first()
            if run is None:
                raise IntegrityError(
                    "run is not visible in namespace",
                    params=None,
                    orig=ValueError("run is not visible in namespace"),
                )
            connection.execute(
                text(
                    """
                    INSERT INTO invocations (
                        id, run_id, scope_id, node_id, status, input_json,
                        input_digest, version, created_at, updated_at
                    ) VALUES (
                        :invocation_id, :run_id, :scope_id, :node_id, 'planned',
                        :input_json, :input_digest, 1, :now, :now
                    )
                    """
                ),
                {
                    "invocation_id": invocation_id,
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "node_id": node_id,
                    "input_json": input_json,
                    "input_digest": input_digest,
                    "now": now,
                },
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=self._next_event_sequence(connection, run_id),
                event_type="invocation.created",
                payload={
                    "invocationId": invocation_id,
                    "nodeId": node_id,
                    "status": "planned",
                },
                scope_id=scope_id,
                invocation_id=invocation_id,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO attempts (
                        id, run_id, scope_id, invocation_id, attempt_no, status,
                        input_json, input_digest, dispatch_key, effect_key,
                        version, created_at, updated_at
                    ) VALUES (
                        :attempt_id, :run_id, :scope_id, :invocation_id,
                        :attempt_no, 'created', :input_json, :input_digest,
                        :dispatch_key, :effect_key, 1, :now, :now
                    )
                    """
                ),
                {
                    "attempt_id": attempt_id,
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "invocation_id": invocation_id,
                    "attempt_no": attempt_no,
                    "input_json": input_json,
                    "input_digest": input_digest,
                    "dispatch_key": dispatch_key,
                    "effect_key": effect_key,
                    "now": now,
                },
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=self._next_event_sequence(connection, run_id),
                event_type="attempt.created",
                payload={
                    "attemptId": attempt_id,
                    "attemptNo": attempt_no,
                    "status": "created",
                },
                scope_id=scope_id,
                invocation_id=invocation_id,
                attempt_id=attempt_id,
            )
        invocation = self.get_invocation(namespace, invocation_id)
        attempt = self.get_attempt(namespace, attempt_id)
        if invocation is None or attempt is None:
            raise RuntimeError("invocation or attempt disappeared after commit")
        return invocation, attempt

    def create_human_request(
        self,
        *,
        namespace: str,
        run_id: str,
        scope_id: str,
        invocation_id: str,
        request_type: str,
        title: str,
        instructions: str,
        input_value: Any,
        subject_digest: str,
        choices: list[str],
        decision_schema: dict[str, Any],
        authorized_subjects: list[str],
        expires_at: str,
    ) -> dict[str, Any]:
        if not namespace.strip() or not run_id.strip() or not scope_id.strip():
            raise ValueError("namespace, run_id and scope_id are required")
        if not invocation_id.strip() or not request_type.strip():
            raise ValueError("invocation_id and request_type are required")
        if request_type not in {"approval", "review", "input"}:
            raise ValueError("human request type must be approval, review or input")
        if request_type in {"approval", "review"} and not choices:
            raise ValueError("approval/review request requires choices")
        if request_type == "input" and choices:
            raise ValueError("input request choices must be empty")
        if not authorized_subjects:
            raise ValueError("human request requires authorized subjects")
        try:
            Draft202012Validator.check_schema(decision_schema)
        except SchemaError as exc:
            raise ValueError("human decision schema is invalid") from exc
        if _parse_timestamp(expires_at) <= _parse_timestamp(_now()):
            raise ValueError("human request expiry must be in the future")
        input_json = _json(input_value)
        request_id = _new_id("human")
        now = _now()
        with self._store.transaction() as connection:
            run = connection.execute(
                text(
                    "SELECT id FROM runs "
                    "WHERE id = :run_id AND namespace = :namespace "
                    "FOR UPDATE"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).mappings().first()
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            scope = connection.execute(
                text("SELECT run_id FROM scopes WHERE id = :scope_id"),
                {"scope_id": scope_id},
            ).mappings().first()
            if scope is None or scope["run_id"] != run_id:
                raise ValueError("human request scope does not belong to run")
            invocation = connection.execute(
                text(
                    "SELECT run_id, scope_id FROM invocations "
                    "WHERE id = :invocation_id"
                ),
                {"invocation_id": invocation_id},
            ).mappings().first()
            if (
                invocation is None
                or invocation["run_id"] != run_id
                or invocation["scope_id"] != scope_id
            ):
                raise ValueError("human request invocation does not match scope")
            connection.execute(
                text(
                    """
                    INSERT INTO human_requests (
                        id, run_id, scope_id, invocation_id, request_type, title,
                        instructions, input_json, input_digest, subject_digest,
                        choices_json, decision_schema_json, authorized_subjects_json,
                        created_at, expires_at, version, status, decision_id,
                        updated_at
                    ) VALUES (
                        :request_id, :run_id, :scope_id, :invocation_id,
                        :request_type, :title, :instructions, :input_json,
                        :input_digest, :subject_digest, :choices_json,
                        :decision_schema_json, :authorized_subjects_json,
                        :now, :expires_at, 1, 'pending', NULL, :now
                    )
                    """
                ),
                {
                    "request_id": request_id,
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "invocation_id": invocation_id,
                    "request_type": request_type,
                    "title": title,
                    "instructions": instructions,
                    "input_json": input_json,
                    "input_digest": _digest(input_json),
                    "subject_digest": subject_digest,
                    "choices_json": _json(choices),
                    "decision_schema_json": _json(decision_schema),
                    "authorized_subjects_json": _json(authorized_subjects),
                    "now": now,
                    "expires_at": expires_at,
                },
            )
            self._insert_event(
                connection,
                run_id=run_id,
                sequence=self._next_event_sequence(connection, run_id),
                event_type="human.created",
                payload={"requestId": request_id, "status": "pending"},
                scope_id=scope_id,
                invocation_id=invocation_id,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id,
                        invocation_id, not_before, payload_json, status,
                        worker_id, claimed_at, created_at, updated_at
                    ) VALUES (
                        :wait_id, :namespace, :wait_key, 'human',
                        :run_id, :scope_id, :invocation_id, :expires_at,
                        :payload_json, 'pending', NULL, NULL, :now, :now
                    )
                    """
                ),
                {
                    "wait_id": _new_id("wait"),
                    "namespace": namespace,
                    "wait_key": f"human:{request_id}",
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "invocation_id": invocation_id,
                    "expires_at": expires_at,
                    "payload_json": _json({"requestId": request_id}),
                    "now": now,
                },
            )
        request = self.get_human_request(namespace, request_id)
        if request is None:
            raise RuntimeError("human request disappeared after commit")
        return request

    def get_human_request(
        self, namespace: str, request_id: str
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT human_requests.* FROM human_requests
                    JOIN runs ON runs.id = human_requests.run_id
                    WHERE human_requests.id = :request_id
                      AND runs.namespace = :namespace
                    """
                ),
                {"request_id": request_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def list_human_requests(
        self,
        *,
        namespace: str,
        run_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["runs.namespace = :namespace"]
        parameters: dict[str, Any] = {"namespace": namespace}
        if run_id is not None:
            conditions.append("human_requests.run_id = :run_id")
            parameters["run_id"] = run_id
        if status is not None:
            conditions.append("human_requests.status = :status")
            parameters["status"] = status
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT human_requests.* FROM human_requests "
                    "JOIN runs ON runs.id = human_requests.run_id "
                    "WHERE " + " AND ".join(conditions) +
                    " ORDER BY human_requests.created_at, human_requests.id"
                ),
                parameters,
            ).mappings().all()
        return [dict(row) for row in rows]

    def get_human_decision(
        self, namespace: str, request_id: str
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT human_decisions.* FROM human_decisions
                    JOIN human_requests ON human_requests.id = human_decisions.request_id
                    JOIN runs ON runs.id = human_requests.run_id
                    WHERE human_decisions.request_id = :request_id
                      AND runs.namespace = :namespace
                    """
                ),
                {"request_id": request_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_human_decision_by_idempotency_key(
        self, namespace: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT human_decisions.* FROM human_decisions
                    JOIN human_requests ON human_requests.id = human_decisions.request_id
                    JOIN runs ON runs.id = human_requests.run_id
                    WHERE human_decisions.namespace = :namespace
                      AND human_decisions.idempotency_key = :idempotency_key
                      AND runs.namespace = :namespace
                    """
                ),
                    {"idempotency_key": idempotency_key, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_human_progress_intent(
        self, namespace: str, request_id: str
    ) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT human_progress_intents.* FROM human_progress_intents
                    JOIN runs ON runs.id = human_progress_intents.run_id
                    WHERE human_progress_intents.request_id = :request_id
                      AND runs.namespace = :namespace
                    """
                ),
                {"request_id": request_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def decide_human_request(
        self,
        *,
        namespace: str,
        request_id: str,
        choice: str | None = None,
        decision: Any | None = None,
        comment: str = "",
        expected_version: int,
        subject_digest: str,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if self._expire_human_request_if_due(namespace, request_id):
            raise ValueError("human request has expired")
        with self._store.transaction() as connection:
            previous = connection.execute(
                text(
                    """
                    SELECT human_decisions.* FROM human_decisions
                    JOIN human_requests ON human_requests.id = human_decisions.request_id
                    JOIN runs ON runs.id = human_requests.run_id
                    WHERE human_decisions.idempotency_key = :idempotency_key
                      AND runs.namespace = :namespace
                    """
                ),
                {"idempotency_key": idempotency_key, "namespace": namespace},
            ).mappings().first()
            if previous is not None:
                if previous["request_id"] != request_id:
                    raise ValueError("idempotency key belongs to another request")
                existing = connection.execute(
                    text("SELECT * FROM human_requests WHERE id = :request_id"),
                    {"request_id": request_id},
                ).mappings().one()
                if (
                    previous["actor"] != actor
                    or previous["subject_digest"] != subject_digest
                    or previous["request_version"] != expected_version + 1
                    or previous["choice"] != (choice or "")
                    or previous["comment"] != comment
                    or previous["decision_json"]
                    != _json(
                        {"decision": choice, "comment": comment}
                        if existing["request_type"] in {"approval", "review"}
                        else decision
                    )
                ):
                    raise ValueError("idempotency key was reused with different content")
                return dict(existing)
            request = connection.execute(
                text(
                    """
                    SELECT human_requests.* FROM human_requests
                    JOIN runs ON runs.id = human_requests.run_id
                    WHERE human_requests.id = :request_id
                      AND runs.namespace = :namespace
                    """
                ),
                {"request_id": request_id, "namespace": namespace},
            ).mappings().first()
            if request is None:
                raise KeyError(f"human request not found: {request_id}")
            connection.execute(
                text("SELECT id FROM runs WHERE id = :run_id FOR UPDATE"),
                {"run_id": request["run_id"]},
            )
            request = connection.execute(
                text("SELECT * FROM human_requests WHERE id = :request_id FOR UPDATE"),
                {"request_id": request_id},
            ).mappings().one()
            if int(request["version"]) != expected_version:
                raise ValueError("human request version conflict")
            if request["status"] != "pending":
                raise ValueError("human request is not pending")
            if request["subject_digest"] != subject_digest:
                raise ValueError("human request subject conflict")
            if actor not in json.loads(request["authorized_subjects_json"]):
                raise ValueError("actor is not authorized")
            if request["request_type"] in {"approval", "review"}:
                if choice not in json.loads(request["choices_json"]):
                    raise ValueError("choice is not allowed")
                stored_decision = {"decision": choice, "comment": comment}
            else:
                if decision is None:
                    raise ValueError("input request requires a structured decision")
                choice = ""
                stored_decision = decision
            try:
                Draft202012Validator(json.loads(request["decision_schema_json"])).validate(
                    stored_decision
                )
            except ValidationError as exc:
                raise ValueError("human decision does not match decision schema") from exc
            if _parse_timestamp(request["expires_at"]) <= _parse_timestamp(_now()):
                raise ValueError("human request is expired")
            decision_id = _new_id("decision")
            version = int(request["version"]) + 1
            now = _now()
            connection.execute(
                text(
                    """
                    INSERT INTO human_decisions (
                        id, namespace, request_id, request_version, choice, comment,
                        decision_json, actor, subject_digest, idempotency_key,
                        created_at
                    ) VALUES (
                        :decision_id, :namespace, :request_id, :request_version, :choice,
                        :comment, :decision_json, :actor, :subject_digest,
                        :idempotency_key, :now
                    )
                    """
                ),
                {
                    "decision_id": decision_id,
                    "namespace": namespace,
                    "request_id": request_id,
                    "request_version": version,
                    "choice": choice,
                    "comment": comment,
                    "decision_json": _json(stored_decision),
                    "actor": actor,
                    "subject_digest": subject_digest,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE human_requests
                    SET status = 'decided', version = :version,
                        decision_id = :decision_id, updated_at = :now
                    WHERE id = :request_id AND status = 'pending'
                    """
                ),
                {
                    "version": version,
                    "decision_id": decision_id,
                    "now": now,
                    "request_id": request_id,
                },
            )
            self._insert_event(
                connection,
                run_id=request["run_id"],
                sequence=self._next_event_sequence(connection, request["run_id"]),
                event_type="human.decided",
                payload={
                    "requestId": request_id,
                    "choice": choice,
                    "version": version,
                },
                scope_id=request["scope_id"],
                invocation_id=request["invocation_id"],
            )
            connection.execute(
                text(
                    """
                    UPDATE waits SET status = 'completed', updated_at = :now
                    WHERE namespace = :namespace AND wait_key = :wait_key
                      AND status IN ('pending', 'claimed')
                    """
                ),
                {
                    "namespace": namespace,
                    "wait_key": f"human:{request_id}",
                    "now": now,
                },
            )
            intent_id = _new_id("intent")
            connection.execute(
                text(
                    """
                    INSERT INTO human_progress_intents (
                        id, request_id, run_id, scope_id, invocation_id,
                        decision_id, action, status, created_at, updated_at
                    ) VALUES (
                        :intent_id, :request_id, :run_id, :scope_id,
                        :invocation_id, :decision_id, 'resume-human-decision',
                        'pending', :now, :now
                    )
                    """
                ),
                {
                    "intent_id": intent_id,
                    "request_id": request_id,
                    "run_id": request["run_id"],
                    "scope_id": request["scope_id"],
                    "invocation_id": request["invocation_id"],
                    "decision_id": decision_id,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id,
                        invocation_id, not_before, payload_json, status,
                        worker_id, claimed_at, created_at, updated_at
                    ) VALUES (
                        :wait_id, :namespace, :wait_key, 'human-progress',
                        :run_id, :scope_id, :invocation_id, :now, :payload_json,
                        'pending', NULL, NULL, :now, :now
                    )
                    """
                ),
                {
                    "wait_id": _new_id("wait"),
                    "namespace": namespace,
                    "wait_key": f"human-progress:{request_id}",
                    "run_id": request["run_id"],
                    "scope_id": request["scope_id"],
                    "invocation_id": request["invocation_id"],
                    "now": now,
                    "payload_json": _json({"requestId": request_id}),
                },
            )
            result = connection.execute(
                text("SELECT * FROM human_requests WHERE id = :request_id"),
                {"request_id": request_id},
            ).mappings().one()
            return dict(result)

    def register_external_artifact_metadata(
        self,
        *,
        namespace: str,
        attempt_id: str,
        execution_ref: str,
        artifacts: list[dict[str, Any]],
    ) -> list[str]:
        required = {
            "artifactId",
            "version",
            "executionRef",
            "namespace",
            "name",
            "mediaType",
            "sizeBytes",
            "digest",
        }
        if any(not isinstance(item, dict) or set(item) != required for item in artifacts):
            raise ValueError("artifact metadata shape is invalid")
        if any(
            item["executionRef"] != execution_ref or item["namespace"] != namespace
            for item in artifacts
        ):
            raise ValueError("artifact metadata identity mismatch")
        validate_artifact_metadata(artifacts, execution_ref, namespace)
        refs: list[str] = []
        with self._store.transaction() as connection:
            attempt_row = connection.execute(
                text(
                    """
                    SELECT * FROM attempts
                    WHERE id = :attempt_id
                    FOR UPDATE
                    """
                ),
                {"attempt_id": attempt_id},
            ).mappings().first()
            if attempt_row is None or attempt_row["external_ref"] != execution_ref:
                raise ValueError("artifact source does not match attempt")
            run = connection.execute(
                text(
                    "SELECT * FROM runs WHERE id = :run_id AND namespace = :namespace "
                    "FOR UPDATE"
                ),
                {"run_id": attempt_row["run_id"], "namespace": namespace},
            ).mappings().first()
            if run is None:
                raise KeyError(f"run not found: {attempt_row['run_id']}")
            observation = json.loads(attempt_row["observation_json"] or "null")
            if (
                not isinstance(observation, dict)
                or observation.get("status") != "succeeded"
                or observation.get("executionFinal") is not True
                or observation.get("executionRef") != execution_ref
                or observation.get("artifacts") != artifacts
            ):
                raise ValueError("artifact metadata differs from persisted observation")
            for item in artifacts:
                source_key = (
                    attempt_id,
                    execution_ref,
                    item["artifactId"],
                    item["version"],
                )
                existing = connection.execute(
                    text(
                        """
                        SELECT * FROM external_artifact_sources
                        WHERE attempt_id = :attempt_id
                          AND execution_ref = :execution_ref
                          AND source_artifact_id = :source_artifact_id
                          AND version = :version
                        """
                    ),
                    {
                        "attempt_id": source_key[0],
                        "execution_ref": source_key[1],
                        "source_artifact_id": source_key[2],
                        "version": source_key[3],
                    },
                ).mappings().first()
                if existing is not None:
                    if existing["metadata_json"] != _json(item):
                        raise ValueError("artifact source metadata conflict")
                    refs.append(str(existing["artifact_id"]))
                    continue
                artifact_id = _new_id("artifact")
                connection.execute(
                    text(
                        """
                        INSERT INTO artifacts (
                            id, namespace, run_id, invocation_id, name, media_type,
                            size_bytes, digest, storage_ref, status, created_at
                        ) VALUES (
                            :artifact_id, :namespace, :run_id, :invocation_id,
                            :name, :media_type, :size_bytes, :digest,
                            :storage_ref, 'external', :now
                        )
                        """
                    ),
                    {
                        "artifact_id": artifact_id,
                        "namespace": namespace,
                    "run_id": run["id"],
                    "invocation_id": attempt_row["invocation_id"],
                        "name": item["name"],
                        "media_type": item["mediaType"],
                        "size_bytes": item["sizeBytes"],
                        "digest": item["digest"],
                        "storage_ref": (
                            f"external:{execution_ref}:{item['artifactId']}:{item['version']}"
                        ),
                        "now": _now(),
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO external_artifact_sources (
                            attempt_id, execution_ref, source_artifact_id,
                            version, metadata_json, artifact_id
                        ) VALUES (
                            :attempt_id, :execution_ref, :source_artifact_id,
                            :version, :metadata_json, :artifact_id
                        )
                        """
                    ),
                    {
                        "attempt_id": source_key[0],
                        "execution_ref": source_key[1],
                        "source_artifact_id": source_key[2],
                        "version": source_key[3],
                        "metadata_json": _json(item),
                        "artifact_id": artifact_id,
                    },
                )
                self._insert_event(
                    connection,
                    run_id=run["id"],
                    sequence=self._next_event_sequence(connection, run["id"]),
                    event_type="artifact.created",
                    payload={
                        "artifactId": artifact_id,
                        "digest": item["digest"],
                        "status": "external",
                    },
                    invocation_id=attempt_row["invocation_id"],
                    attempt_id=attempt_id,
                )
                refs.append(artifact_id)
        return refs

    def get_artifact(self, namespace: str, artifact_id: str) -> dict[str, Any] | None:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM artifacts "
                    "WHERE id = :artifact_id AND namespace = :namespace"
                ),
                {"artifact_id": artifact_id, "namespace": namespace},
            ).mappings().first()
        return dict(row) if row is not None else None

    def list_artifacts(self, namespace: str, run_id: str) -> list[dict[str, Any]]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM artifacts "
                    "WHERE namespace = :namespace AND run_id = :run_id "
                    "ORDER BY created_at, id"
                ),
                {"namespace": namespace, "run_id": run_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def validate_artifact_refs(
        self, namespace: str, run_id: str, artifact_refs: list[str]
    ) -> None:
        run = self.get_run(namespace, run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        for artifact_id in artifact_refs:
            artifact = self.get_artifact(namespace, artifact_id)
            if artifact is None or artifact["run_id"] != run_id:
                raise ValueError(f"artifact is not authorized for run: {artifact_id}")

    def _expire_human_request_if_due(self, namespace: str, request_id: str) -> bool:
        with self._store.transaction() as connection:
            request = connection.execute(
                text(
                    """
                    SELECT human_requests.* FROM human_requests
                    JOIN runs ON runs.id = human_requests.run_id
                    WHERE human_requests.id = :request_id
                      AND runs.namespace = :namespace
                    FOR UPDATE
                    """
                ),
                {"request_id": request_id, "namespace": namespace},
            ).mappings().first()
            if request is None or request["status"] != "pending":
                return False
            connection.execute(
                text("SELECT id FROM runs WHERE id = :run_id FOR UPDATE"),
                {"run_id": request["run_id"]},
            )
            now = _now()
            if _parse_timestamp(request["expires_at"]) > _parse_timestamp(now):
                return False
            version = int(request["version"]) + 1
            connection.execute(
                text(
                    """
                    UPDATE human_requests
                    SET status = 'expired', version = :version, updated_at = :now
                    WHERE id = :request_id AND status = 'pending'
                    """
                ),
                {"version": version, "now": now, "request_id": request_id},
            )
            connection.execute(
                text(
                    """
                    UPDATE waits SET status = 'cancelled', updated_at = :now
                    WHERE namespace = :namespace AND wait_key = :wait_key
                      AND status IN ('pending', 'claimed')
                    """
                ),
                {
                    "namespace": namespace,
                    "wait_key": f"human:{request_id}",
                    "now": now,
                },
            )
            self._insert_event(
                connection,
                run_id=request["run_id"],
                sequence=self._next_event_sequence(connection, request["run_id"]),
                event_type="human.expired",
                payload={"requestId": request_id, "status": "expired"},
                scope_id=request["scope_id"],
                invocation_id=request["invocation_id"],
            )
            return True

    def ensure_submit_outbox(
        self,
        *,
        namespace: str,
        attempt_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload_json = _json(payload)
        payload_digest = _digest(payload_json)
        action_key = f"submit:{attempt_id}"
        with self._store.transaction() as connection:
            attempt = connection.execute(
                text(
                    "SELECT attempts.*, runs.namespace FROM attempts "
                    "JOIN runs ON runs.id = attempts.run_id "
                    "WHERE attempts.id = :attempt_id AND runs.namespace = :namespace"
                ),
                {"attempt_id": attempt_id, "namespace": namespace},
            ).mappings().first()
            if attempt is None:
                raise KeyError(f"attempt not found: {attempt_id}")
            connection.execute(
                text("SELECT id FROM runs WHERE id = :run_id FOR UPDATE"),
                {"run_id": attempt["run_id"]},
            )
            now = _now()
            outbox_id = _new_id("outbox")
            inserted = connection.execute(
                text(
                    """
                    INSERT INTO outbox (
                        id, action_key, namespace, run_id, scope_id, invocation_id,
                        attempt_id, action, payload_json, payload_digest, status,
                        attempt_count, created_at, updated_at
                    ) VALUES (
                        :outbox_id, :action_key, :namespace, :run_id, :scope_id,
                        :invocation_id, :attempt_id, 'submit', :payload_json,
                        :payload_digest, 'pending', 0, :now, :now
                    )
                    ON CONFLICT (action_key) DO NOTHING
                    RETURNING *
                    """
                ),
                {
                    "outbox_id": outbox_id,
                    "action_key": action_key,
                    "namespace": namespace,
                    "run_id": attempt["run_id"],
                    "scope_id": attempt["scope_id"],
                    "invocation_id": attempt["invocation_id"],
                    "attempt_id": attempt_id,
                    "payload_json": payload_json,
                    "payload_digest": payload_digest,
                    "now": now,
                },
            ).mappings().first()
            if inserted is None:
                existing = connection.execute(
                    text("SELECT * FROM outbox WHERE action_key = :action_key"),
                    {"action_key": action_key},
                ).mappings().first()
                if existing is None:
                    raise RuntimeError("submit outbox conflict row disappeared")
                if existing["payload_digest"] != payload_digest:
                    raise IntegrityError(
                        "submit outbox payload conflict",
                        params=None,
                        orig=ValueError("submit outbox payload conflict"),
                    )
                self._ensure_submit_wait(
                    connection,
                    namespace=namespace,
                    action_key=action_key,
                    attempt=attempt,
                    outbox_id=str(existing["id"]),
                    not_before=_now(),
                )
                return dict(existing)
            self._insert_event(
                connection,
                run_id=attempt["run_id"],
                sequence=self._next_event_sequence(connection, attempt["run_id"]),
                event_type="execution.submit_intent.created",
                payload={
                    "attemptId": attempt_id,
                    "dispatchKey": attempt["dispatch_key"],
                    "payloadDigest": payload_digest,
                },
                scope_id=attempt["scope_id"],
                invocation_id=attempt["invocation_id"],
                attempt_id=attempt_id,
            )
            self._ensure_submit_wait(
                connection,
                namespace=namespace,
                action_key=action_key,
                attempt=attempt,
                outbox_id=outbox_id,
                not_before=now,
            )
            return dict(inserted)

    @staticmethod
    def _ensure_submit_wait(
        connection: Connection,
        *,
        namespace: str,
        action_key: str,
        attempt: Any,
        outbox_id: str,
        not_before: str,
    ) -> None:
        existing = connection.execute(
            text(
                "SELECT id, status FROM waits "
                "WHERE namespace = :namespace AND wait_key = :wait_key"
            ),
            {"namespace": namespace, "wait_key": action_key},
        ).mappings().first()
        if existing is None:
            connection.execute(
                text(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id,
                        invocation_id, not_before, payload_json, status,
                        created_at, updated_at
                    ) VALUES (
                        :wait_id, :namespace, :wait_key, 'external-submit',
                        :run_id, :scope_id, :invocation_id, :now, :payload_json,
                        'pending', :now, :now
                    )
                    """
                ),
                {
                    "wait_id": _new_id("wait"),
                    "namespace": namespace,
                    "wait_key": action_key,
                    "run_id": attempt["run_id"],
                    "scope_id": attempt["scope_id"],
                    "invocation_id": attempt["invocation_id"],
                    "now": not_before,
                    "payload_json": _json(
                        {"outboxId": outbox_id, "attemptId": attempt["id"]}
                    ),
                },
            )
        elif existing["status"] == "cancelled":
            connection.execute(
                text(
                    """
                    UPDATE waits
                    SET status = 'pending', not_before = :not_before,
                        worker_id = NULL, claimed_at = NULL, updated_at = :updated_at
                    WHERE id = :wait_id
                    """
                ),
                {
                    "not_before": not_before,
                    "updated_at": _now(),
                    "wait_id": existing["id"],
                },
            )

    def close(self) -> None:
        self._store.close()

    @staticmethod
    def _insert_event(
        connection: Connection,
        *,
        run_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
        scope_id: str | None = None,
        invocation_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO run_events (
                    id, run_id, scope_id, invocation_id, attempt_id, seq,
                    type, payload_json, occurred_at
                ) VALUES (
                    :event_id, :run_id, :scope_id, :invocation_id, :attempt_id,
                    :sequence, :event_type, :payload_json, :occurred_at
                )
                """
            ),
            {
                "event_id": _new_id("event"),
                "run_id": run_id,
                "scope_id": scope_id,
                "invocation_id": invocation_id,
                "attempt_id": attempt_id,
                "sequence": sequence,
                "event_type": event_type,
                "payload_json": _json(payload),
                "occurred_at": _now(),
            },
        )

    @staticmethod
    def _next_event_sequence(connection: Connection, run_id: str) -> int:
        value: Any = connection.execute(
            text("SELECT COALESCE(MAX(seq), 0) + 1 FROM run_events WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()
        return int(value)

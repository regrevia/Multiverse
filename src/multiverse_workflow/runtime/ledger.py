from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from multiverse_workflow.runtime.http_job import (
    validate_artifact_content,
    validate_artifact_metadata,
)

_UNSET = object()


class LedgerConflict(RuntimeError):
    """A persisted command cannot be applied to the current resource version."""


def new_id(prefix: str) -> str:
    return _new_id(prefix)


class Ledger:
    def __init__(self, database_path: Path) -> None:
        database_path = database_path.expanduser().resolve()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._artifact_root = database_path.parent / "artifacts"
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def create_run(
        self,
        *,
        namespace: str,
        deployment_id: str | None = None,
        workflow_id: str,
        package_digest: str,
        binding_digest: str | None,
        plan: dict[str, Any],
        input_value: Any,
        deadline_at: str,
        run_id: str | None = None,
        rerun_of: str | None = None,
        rerun_reason: str | None = None,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or _new_id("run")
        now = _now()
        input_json = _json(input_value)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, namespace, deployment_id, workflow_id, package_digest, binding_digest,
                    plan_json, input_json, input_digest, status, control_mode,
                    deadline_at, version, current_node_id, rerun_of, rerun_reason,
                    current_scope_id, current_invocation_id, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'run', ?, 1, NULL,
                    ?, ?, NULL, NULL, ?, ?
                )
                """,
                (
                    run_id,
                    namespace,
                    deployment_id,
                    workflow_id,
                    package_digest,
                    binding_digest,
                    _json(plan),
                    input_json,
                    _digest(input_json),
                    deadline_at,
                    rerun_of,
                    rerun_reason,
                    now,
                    now,
                ),
            )
            self._event(
                connection,
                run_id,
                "run.created",
                {"status": "queued", "workflowId": workflow_id},
            )
            if command_id is not None:
                updated = connection.execute(
                    """
                    UPDATE commands
                    SET after_version = 1, transition = 'run.created', updated_at = ?
                    WHERE id = ? AND status = 'accepted'
                    """,
                    (_now(), command_id),
                )
                if updated.rowcount != 1:
                    raise LedgerConflict("run creation command is not accepted")
        return self.get_run(run_id)  # type: ignore[return-value]

    def create_queued_run(
        self,
        *,
        namespace: str,
        deployment_id: str | None = None,
        workflow_id: str,
        package_digest: str,
        binding_digest: str | None,
        plan: dict[str, Any],
        input_value: Any,
        deadline_at: str,
        entry_node_id: str,
        run_id: str | None = None,
        rerun_of: str | None = None,
        rerun_reason: str | None = None,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically persist a queued Run, root Scope, and start wake."""
        run_id = run_id or _new_id("run")
        scope_id = _new_id("scope")
        wait_id = _new_id("wait")
        now = _now()
        input_json = _json(input_value)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, namespace, deployment_id, workflow_id, package_digest, binding_digest,
                    plan_json, input_json, input_digest, status, control_mode,
                    deadline_at, version, current_node_id, rerun_of, rerun_reason,
                    current_scope_id, current_invocation_id, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'run', ?, 1, ?,
                    ?, ?, NULL, NULL, ?, ?
                )
                """,
                (
                    run_id,
                    namespace,
                    deployment_id,
                    workflow_id,
                    package_digest,
                    binding_digest,
                    _json(plan),
                    input_json,
                    _digest(input_json),
                    deadline_at,
                    entry_node_id,
                    rerun_of,
                    rerun_reason,
                    now,
                    now,
                ),
            )
            self._event(
                connection,
                run_id,
                "run.created",
                {"status": "queued", "workflowId": workflow_id},
            )
            connection.execute(
                """
                INSERT INTO scopes (
                    id, run_id, parent_scope_id, parent_invocation_id,
                    workflow_id, path_json, input_json, input_digest, status, created_at
                ) VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    scope_id,
                    run_id,
                    workflow_id,
                    _json(["root"]),
                    input_json,
                    _digest(input_json),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE runs
                SET current_scope_id = ?, current_node_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (scope_id, entry_node_id, now, run_id),
            )
            self._event(
                connection,
                run_id,
                "scope.created",
                {
                    "scopeId": scope_id,
                    "workflowId": workflow_id,
                    "inputDigest": _digest(input_json),
                },
                scope_id=scope_id,
            )
            connection.execute(
                """
                INSERT INTO waits (
                    id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                    not_before, payload_json, status, worker_id, claimed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'run-start', ?, ?, NULL, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (
                    wait_id,
                    namespace,
                    f"run-start:{run_id}",
                    run_id,
                    scope_id,
                    now,
                    _json({"runId": run_id, "scopeId": scope_id}),
                    now,
                    now,
                ),
            )
            if command_id is not None:
                updated = connection.execute(
                    """
                    UPDATE commands
                    SET after_version = 1, transition = 'run.created', updated_at = ?
                    WHERE id = ? AND status = 'accepted'
                    """,
                    (_now(), command_id),
                )
                if updated.rowcount != 1:
                    raise LedgerConflict("run creation command is not accepted")
        return self.get_run(run_id)  # type: ignore[return-value]

    def create_command(
        self,
        *,
        command_id: str,
        idempotency_key: str,
        fingerprint: str,
        operation: str,
        namespace: str,
        resource_id: str,
        subject: str = "local-user",
    ) -> dict[str, Any]:
        now = _now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO commands (
                    id, idempotency_key, fingerprint, operation, namespace,
                    subject, resource_id, status, resource_version, error_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', NULL, NULL, ?, ?)
                """,
                (
                    command_id,
                    idempotency_key,
                    fingerprint,
                    operation,
                    namespace,
                    subject,
                    resource_id,
                    now,
                    now,
                ),
            )
        return self.get_command(command_id)  # type: ignore[return-value]

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM commands WHERE id = ?", (command_id,)
        ).fetchone()
        return _row(row)

    def get_command_by_key(
        self,
        idempotency_key: str,
        *,
        namespace: str | None = None,
        subject: str | None = None,
        operation: str | None = None,
    ) -> dict[str, Any] | None:
        if namespace is None or subject is None or operation is None:
            row = self._connection.execute(
                "SELECT * FROM commands WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return _row(row)
        row = self._connection.execute(
            """
            SELECT * FROM commands
            WHERE idempotency_key = ? AND namespace = ?
              AND subject = ? AND operation = ?
            """,
            (idempotency_key, namespace, subject, operation),
        ).fetchone()
        return _row(row)

    def list_commands_by_key(
        self,
        idempotency_key: str,
        *,
        namespace: str | None = None,
        subject: str | None = None,
        operation: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["idempotency_key = ?"]
        parameters: list[str] = [idempotency_key]
        if namespace is not None:
            clauses.append("namespace = ?")
            parameters.append(namespace)
        if subject is not None:
            clauses.append("subject = ?")
            parameters.append(subject)
        if operation is not None:
            clauses.append("operation = ?")
            parameters.append(operation)
        rows = self._connection.execute(
            f"""
            SELECT * FROM commands
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at, id
            """,
            parameters,
        ).fetchall()
        return [command for row in rows if (command := _row(row)) is not None]

    def finish_command(
        self,
        command_id: str,
        *,
        status: Literal["completed", "rejected"],
        resource_version: int | None = None,
        error: Any = None,
    ) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE id = ?", (command_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"command not found: {command_id}")
            connection.execute(
                """
                UPDATE commands
                SET status = ?, resource_version = ?, error_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    resource_version,
                    _json_or_none(error),
                    _now(),
                    command_id,
                ),
            )
        return self.get_command(command_id)  # type: ignore[return-value]

    def control_run(
        self,
        run_id: str,
        *,
        operation: Literal["pause", "resume", "cancel"],
        expected_version: int,
        reason: str,
        command_id: str | None = None,
        enqueue_resume: bool = False,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise LedgerConflict("control reason must not be empty")
        with self._transaction() as connection:
            run = self._require_run(connection, run_id)
            if command_id is not None:
                command = connection.execute(
                    "SELECT * FROM commands WHERE id = ?", (command_id,)
                ).fetchone()
                if command is None:
                    raise LedgerConflict(f"command not found: {command_id}")
                if self._command_applied_for_control(
                    command,
                    run_id=run_id,
                    operation=operation,
                    expected_version=expected_version,
                ):
                    return self.get_run(run_id)  # type: ignore[return-value]
            if int(run["version"]) != expected_version:
                raise LedgerConflict("run version conflict")
            if operation == "pause":
                if run["status"] not in {"queued", "running", "waiting"}:
                    raise LedgerConflict(f"run cannot be paused from status: {run['status']}")
                status = "paused"
                control_mode = "pause"
                event_type = "run.paused"
            elif operation == "resume":
                if run["status"] != "paused" or run["control_mode"] != "pause":
                    raise LedgerConflict("only a paused run can resume")
                status = "running"
                control_mode = "run"
                event_type = "run.resumed"
            else:
                if run["status"] in {"succeeded", "failed", "cancelled"}:
                    raise LedgerConflict("run is already terminal")
                active_attempt = connection.execute(
                    """
                    SELECT 1 FROM attempts
                    WHERE run_id = ?
                      AND status IN ('created', 'submitted', 'running', 'unknown')
                    LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                connection.execute(
                    """
                    UPDATE human_requests
                    SET status = 'cancelled', version = version + 1, updated_at = ?
                    WHERE run_id = ? AND status = 'pending'
                    """,
                    (_now(), run_id),
                )
                connection.execute(
                    """
                    UPDATE waits
                    SET status = 'cancelled', updated_at = ?
                    WHERE run_id = ? AND status IN ('pending', 'claimed')
                    """,
                    (_now(), run_id),
                )
                if active_attempt is None:
                    cancellation_error = _json(
                        {"code": "RUN_CANCELLED", "message": reason}
                    )
                    connection.execute(
                        """
                        UPDATE attempts
                        SET status = 'cancelled', error_json = ?, updated_at = ?
                        WHERE run_id = ? AND status IN ('created', 'waiting')
                        """,
                        (cancellation_error, _now(), run_id),
                    )
                    connection.execute(
                        """
                        UPDATE invocations
                        SET status = 'cancelled', error_json = ?, version = version + 1,
                            updated_at = ?
                        WHERE run_id = ? AND status IN ('planned', 'running', 'waiting')
                        """,
                        (cancellation_error, _now(), run_id),
                    )
                    connection.execute(
                        """
                        UPDATE scopes
                        SET status = 'cancelled', error_json = ?
                        WHERE run_id = ? AND status = 'active'
                        """,
                        (cancellation_error, run_id),
                    )
                    status = "cancelled"
                    event_type = "run.cancelled"
                else:
                    status = "stopping"
                    event_type = "run.cancel_requested"
                control_mode = "cancel"
            version = int(run["version"]) + 1
            connection.execute(
                """
                UPDATE runs
                SET status = ?, control_mode = ?, version = ?, updated_at = ?
                    , next_attempt_at = CASE WHEN ? = 'cancel' THEN NULL ELSE next_attempt_at END
                WHERE id = ?
                """,
                (status, control_mode, version, _now(), operation, run_id),
            )
            self._event(
                connection,
                run_id,
                event_type,
                {
                    "operation": operation,
                    "reason": reason,
                    "status": status,
                    "controlMode": control_mode,
                    "version": version,
                },
            )
            if command_id is not None:
                updated = connection.execute(
                    """
                    UPDATE commands
                    SET before_version = ?, after_version = ?, transition = ?, updated_at = ?
                    WHERE id = ? AND status = 'accepted'
                    """,
                    (expected_version, version, event_type, _now(), command_id),
                )
                if updated.rowcount != 1:
                    raise LedgerConflict("control command is not accepted")
            if operation == "resume" and enqueue_resume:
                now = _now()
                connection.execute(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                        not_before, payload_json, status, worker_id, claimed_at,
                        created_at, updated_at
                    )
                    SELECT ?, namespace, ?, 'run-resume', id, current_scope_id,
                           current_invocation_id, ?, ?, 'pending', NULL, NULL, ?, ?
                    FROM runs
                    WHERE id = ?
                    """,
                    (
                        _new_id("wait"),
                        f"run-resume:{run_id}",
                        now,
                        _json({"runId": run_id}),
                        now,
                        now,
                        run_id,
                    ),
                )
        return self.get_run(run_id)  # type: ignore[return-value]

    @staticmethod
    def _command_applied_for_control(
        command: sqlite3.Row,
        *,
        run_id: str,
        operation: Literal["pause", "resume", "cancel"],
        expected_version: int,
    ) -> bool:
        transitions = (
            {"run.cancel_requested", "run.cancelled"}
            if operation == "cancel"
            else {f"run.{operation}d"}
        )
        return (
            str(command["resource_id"]) == run_id
            and str(command["operation"]) == f"run.{operation}"
            and command["status"] == "accepted"
            and command["before_version"] is not None
            and int(command["before_version"]) == expected_version
            and command["after_version"] is not None
            and int(command["after_version"]) > expected_version
            and str(command["transition"]) in transitions
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row(row)

    def list_queued_runs(
        self,
        *,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if namespace is None:
            rows = self._connection.execute(
                """
                SELECT * FROM runs
                WHERE status = 'queued'
                ORDER BY created_at, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT * FROM runs
                WHERE status = 'queued' AND namespace = ?
                ORDER BY created_at, id
                LIMIT ?
                """,
                (namespace, limit),
            ).fetchall()
        return [run for row in rows if (run := _row(row)) is not None]

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        current_node_id: str | None = None,
        current_scope_id: str | None | object = _UNSET,
        current_invocation_id: str | None | object = _UNSET,
        control_mode: str | None = None,
        output: Any = None,
        error: Any = None,
        next_attempt_at: str | None | object = _UNSET,
    ) -> dict[str, Any]:
        now = _now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"run not found: {run_id}")
            version = int(row["version"]) + 1
            next_control_mode = control_mode or row["control_mode"]
            persisted_next_attempt_at = (
                row["next_attempt_at"]
                if next_attempt_at is _UNSET
                else next_attempt_at
            )
            persisted_scope_id = (
                row["current_scope_id"]
                if current_scope_id is _UNSET
                else current_scope_id
            )
            persisted_invocation_id = (
                row["current_invocation_id"]
                if current_invocation_id is _UNSET
                else current_invocation_id
            )
            if (
                current_invocation_id is _UNSET
                and (
                    current_node_id != row["current_node_id"]
                    or persisted_scope_id != row["current_scope_id"]
                )
                ):
                persisted_invocation_id = None
            if persisted_scope_id is None and persisted_invocation_id is not None:
                raise LedgerConflict(
                    "continuation invocation requires a continuation scope"
                )
            if persisted_scope_id is not None:
                scope = connection.execute(
                    "SELECT id, run_id FROM scopes WHERE id = ?",
                    (persisted_scope_id,),
                ).fetchone()
                if scope is None or scope["run_id"] != run_id:
                    raise LedgerConflict("continuation scope does not belong to run")
            if persisted_invocation_id is not None:
                invocation = connection.execute(
                    """
                    SELECT id, run_id, scope_id, node_id
                    FROM invocations
                    WHERE id = ?
                    """,
                    (persisted_invocation_id,),
                ).fetchone()
                if invocation is None or invocation["run_id"] != run_id:
                    raise LedgerConflict(
                        "continuation invocation does not belong to run"
                    )
                if invocation["scope_id"] != persisted_scope_id:
                    raise LedgerConflict(
                        "continuation invocation does not belong to scope"
                    )
                if invocation["node_id"] != current_node_id:
                    raise LedgerConflict(
                        "continuation invocation node does not match current node"
                    )
            connection.execute(
                """
                UPDATE runs
                SET status = ?, control_mode = ?, current_node_id = ?,
                    current_scope_id = ?, current_invocation_id = ?,
                    output_json = ?, error_json = ?, next_attempt_at = ?,
                    version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    next_control_mode,
                    current_node_id,
                    persisted_scope_id,
                    persisted_invocation_id,
                    _json_or_none(output),
                    _json_or_none(error),
                    persisted_next_attempt_at,
                    version,
                    now,
                    run_id,
                ),
            )
            self._event(
                connection,
                run_id,
                "run.updated",
                {
                    "status": status,
                    "controlMode": next_control_mode,
                    "currentNodeId": current_node_id,
                    "currentScopeId": persisted_scope_id,
                    "currentInvocationId": persisted_invocation_id,
                    "version": version,
                },
            )
        return self.get_run(run_id)  # type: ignore[return-value]

    def create_scope(
        self,
        run_id: str,
        workflow_id: str,
        *,
        path: list[str],
        input_value: Any = None,
        parent_scope_id: str | None = None,
        parent_invocation_id: str | None = None,
    ) -> dict[str, Any]:
        scope_id = _new_id("scope")
        input_json = _json(input_value)
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            connection.execute(
                """
                INSERT INTO scopes (
                    id, run_id, parent_scope_id, parent_invocation_id,
                    workflow_id, path_json, input_json, input_digest, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    scope_id,
                    run_id,
                    parent_scope_id,
                    parent_invocation_id,
                    workflow_id,
                    _json(path),
                    input_json,
                    _digest(input_json),
                    _now(),
                ),
            )
            self._event(
                connection,
                run_id,
                "scope.created",
                {
                    "scopeId": scope_id,
                    "workflowId": workflow_id,
                    "inputDigest": _digest(input_json),
                },
                scope_id=scope_id,
            )
        return self.get_scope(scope_id)  # type: ignore[return-value]

    def get_scope(self, scope_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM scopes WHERE id = ?", (scope_id,)).fetchone()
        return _row(row)

    def list_scopes(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM scopes WHERE run_id = ? ORDER BY created_at, id",
            (run_id,),
        ).fetchall()
        return [scope for row in rows if (scope := _row(row)) is not None]

    def list_child_scopes(self, parent_invocation_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT * FROM scopes
            WHERE parent_invocation_id = ?
            ORDER BY created_at, id
            """,
            (parent_invocation_id,),
        ).fetchall()
        return [scope for row in rows if (scope := _row(row)) is not None]

    def finish_scope(
        self,
        scope_id: str,
        *,
        status: str,
        output: Any = None,
        error: Any = None,
    ) -> dict[str, Any]:
        with self._transaction() as connection:
            scope = self._require_scope_by_id(connection, scope_id)
            connection.execute(
                """
                UPDATE scopes
                SET status = ?, output_json = ?, error_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    _json_or_none(output),
                    _json_or_none(error),
                    scope_id,
                ),
            )
            self._event(
                connection,
                scope["run_id"],
                "scope.updated",
                {"scopeId": scope_id, "status": status},
                scope_id=scope_id,
            )
        return self.get_scope(scope_id)  # type: ignore[return-value]

    def create_invocation(
        self,
        run_id: str,
        scope_id: str,
        node_id: str,
        input_value: Any,
        input_digest: str | None = None,
    ) -> dict[str, Any]:
        invocation_id = _new_id("inv")
        input_json = _json(input_value)
        with self._transaction() as connection:
            self._require_scope(connection, run_id, scope_id)
            connection.execute(
                """
                INSERT INTO invocations (
                    id, run_id, scope_id, node_id, status, input_json,
                    input_digest, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'planned', ?, ?, 1, ?, ?)
                """,
                (
                    invocation_id,
                    run_id,
                    scope_id,
                    node_id,
                    input_json,
                    input_digest or _digest(input_json),
                    _now(),
                    _now(),
                ),
            )
            self._event(
                connection,
                run_id,
                "invocation.created",
                {"invocationId": invocation_id, "nodeId": node_id, "status": "planned"},
                scope_id=scope_id,
                invocation_id=invocation_id,
            )
        return self.get_invocation(invocation_id)  # type: ignore[return-value]

    def get_invocation(self, invocation_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM invocations WHERE id = ?", (invocation_id,)
        ).fetchone()
        return _row(row)

    def get_invocation_for_node(self, scope_id: str, node_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT * FROM invocations
            WHERE scope_id = ? AND node_id = ?
            """,
            (scope_id, node_id),
        ).fetchone()
        return _row(row)

    def list_invocations(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM invocations WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [invocation for row in rows if (invocation := _row(row)) is not None]

    def list_attempts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT * FROM attempts
            WHERE run_id = ?
            ORDER BY created_at, attempt_no
            """,
            (run_id,),
        ).fetchall()
        return [attempt for row in rows if (attempt := _row(row)) is not None]

    def list_scope_invocations(self, scope_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM invocations WHERE scope_id = ? ORDER BY created_at, id",
            (scope_id,),
        ).fetchall()
        return [invocation for row in rows if (invocation := _row(row)) is not None]

    def finish_invocation(
        self,
        invocation_id: str,
        *,
        status: str,
        output: Any = None,
        error: Any = None,
    ) -> dict[str, Any]:
        with self._transaction() as connection:
            row = self._require_invocation(connection, invocation_id)
            if row["status"] in {"succeeded", "failed", "cancelled", "skipped"}:
                raise LedgerConflict(
                    f"invocation is terminal: {row['status']}"
                )
            version = int(row["version"]) + 1
            connection.execute(
                """
                UPDATE invocations
                SET status = ?, output_json = ?, error_json = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    _json_or_none(output),
                    _json_or_none(error),
                    version,
                    _now(),
                    invocation_id,
                ),
            )
            self._event(
                connection,
                row["run_id"],
                "invocation.updated",
                {"invocationId": invocation_id, "status": status, "version": version},
                scope_id=row["scope_id"],
                invocation_id=invocation_id,
            )
        return self.get_invocation(invocation_id)  # type: ignore[return-value]

    def create_attempt(
        self,
        invocation_id: str,
        *,
        input_value: Any,
        dispatch_key: str,
        effect_key: str,
        attempt_no: int | None = None,
    ) -> dict[str, Any]:
        attempt_id = _new_id("attempt")
        input_json = _json(input_value)
        with self._transaction() as connection:
            invocation = self._require_invocation(connection, invocation_id)
            if attempt_no is None:
                current = connection.execute(
                    "SELECT COALESCE(MAX(attempt_no), 0) FROM attempts WHERE invocation_id = ?",
                    (invocation_id,),
                ).fetchone()
                attempt_no = int(current[0]) + 1
            connection.execute(
                """
                INSERT INTO attempts (
                    id, run_id, scope_id, invocation_id, attempt_no, status,
                    input_json, input_digest, dispatch_key, effect_key,
                    version, reconciliation_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'created', ?, ?, ?, ?, 1, NULL, ?, ?)
                """,
                (
                    attempt_id,
                    invocation["run_id"],
                    invocation["scope_id"],
                    invocation_id,
                    attempt_no,
                    input_json,
                    _digest(input_json),
                    dispatch_key,
                    effect_key,
                    _now(),
                    _now(),
                ),
            )
            self._event(
                connection,
                invocation["run_id"],
                "attempt.created",
                {"attemptId": attempt_id, "attemptNo": attempt_no, "status": "created"},
                scope_id=invocation["scope_id"],
                invocation_id=invocation_id,
                attempt_id=attempt_id,
            )
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

    def get_submit_outbox(self, attempt_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM outbox WHERE action_key = ?",
            (f"submit:{attempt_id}",),
        ).fetchone()
        return _row(row)

    def get_outbox(self, outbox_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
        ).fetchone()
        return _row(row)

    def ensure_submit_outbox(
        self,
        *,
        attempt_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload_json = _json(payload)
        payload_digest = _digest(payload_json)
        action_key = f"submit:{attempt_id}"
        with self._transaction() as connection:
            attempt = self._require_attempt(connection, attempt_id)
            existing = connection.execute(
                "SELECT * FROM outbox WHERE action_key = ?",
                (action_key,),
            ).fetchone()
            if existing is not None:
                if existing["payload_digest"] != payload_digest:
                    raise LedgerConflict("submit outbox payload conflict")
            else:
                now = _now()
                connection.execute(
                    """
                    INSERT INTO outbox (
                        id, action_key, namespace, run_id, scope_id, invocation_id,
                        attempt_id, action, payload_json, payload_digest, status,
                        external_ref, attempt_count, next_attempt_at, last_error_json,
                        created_at, updated_at
                    ) VALUES (?, ?, (SELECT namespace FROM runs WHERE id = ?), ?, ?, ?, ?,
                              'submit', ?, ?, 'pending', NULL, 0, ?, NULL, ?, ?)
                    """,
                    (
                        _new_id("outbox"),
                        action_key,
                        attempt["run_id"],
                        attempt["run_id"],
                        attempt["scope_id"],
                        attempt["invocation_id"],
                        attempt_id,
                        payload_json,
                        payload_digest,
                        now,
                        now,
                        now,
                    ),
                )
                self._event(
                    connection,
                    attempt["run_id"],
                    "execution.submit_intent.created",
                    {
                        "attemptId": attempt_id,
                        "dispatchKey": attempt["dispatch_key"],
                        "payloadDigest": payload_digest,
                    },
                    scope_id=attempt["scope_id"],
                    invocation_id=attempt["invocation_id"],
                    attempt_id=attempt_id,
                )
            result = connection.execute(
                "SELECT * FROM outbox WHERE action_key = ?",
                (action_key,),
            ).fetchone()
            if result is None:
                raise LedgerConflict("submit outbox disappeared")
            self._ensure_submit_wait_in_transaction(
                connection,
                outbox_id=result["id"],
                attempt_id=attempt_id,
                not_before=result["next_attempt_at"] or _now(),
            )
        return dict(result)

    def _ensure_submit_wait(
        self,
        *,
        outbox_id: str,
        attempt_id: str,
        not_before: str,
    ) -> dict[str, Any]:
        attempt = self.get_attempt(attempt_id)
        if attempt is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        run = self.get_run(attempt["run_id"])
        if run is None:
            raise KeyError(f"run not found: {attempt['run_id']}")
        with self._transaction() as connection:
            self._ensure_submit_wait_in_transaction(
                connection,
                outbox_id=outbox_id,
                attempt_id=attempt_id,
                not_before=not_before,
            )
        wait_key = f"submit:{attempt_id}"
        wait = self.get_wait_by_key(run["namespace"], wait_key)
        if wait is None:
            raise LedgerConflict("submit wait disappeared")
        return wait

    def _ensure_submit_wait_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        outbox_id: str,
        attempt_id: str,
        not_before: str,
    ) -> None:
        attempt = self._require_attempt(connection, attempt_id)
        run = self._require_run(connection, attempt["run_id"])
        wait_key = f"submit:{attempt_id}"
        existing = connection.execute(
            "SELECT * FROM waits WHERE namespace = ? AND wait_key = ?",
            (run["namespace"], wait_key),
        ).fetchone()
        if existing is None:
            now = _now()
            connection.execute(
                """
                INSERT INTO waits (
                    id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                    not_before, payload_json, status, worker_id, claimed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'external-submit', ?, ?, ?, ?, ?, 'pending',
                          NULL, NULL, ?, ?)
                """,
                (
                    _new_id("wait"),
                    run["namespace"],
                    wait_key,
                    attempt["run_id"],
                    attempt["scope_id"],
                    attempt["invocation_id"],
                    not_before,
                    _json({"outboxId": outbox_id, "attemptId": attempt_id}),
                    now,
                    now,
                ),
            )
        elif existing["status"] == "cancelled":
            connection.execute(
                """
                UPDATE waits SET status = 'pending', not_before = ?,
                    worker_id = NULL, claimed_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (not_before, _now(), existing["id"]),
            )

    def claim_submit_outbox(self, outbox_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE outbox
                SET status = 'submitting', attempt_count = attempt_count + 1,
                    updated_at = ?
                WHERE id = ? AND status IN ('pending', 'unknown')
                """,
                (_now(), outbox_id),
            )
            if updated.rowcount != 1:
                row = connection.execute(
                    "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"outbox not found: {outbox_id}")
                return dict(row)
        row = self._connection.execute(
            "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"outbox not found: {outbox_id}")
        return dict(row)

    def mark_submit_outbox_submitted(
        self,
        outbox_id: str,
        *,
        external_ref: str,
    ) -> dict[str, Any]:
        if not external_ref.strip():
            raise LedgerConflict("external execution reference is required")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"outbox not found: {outbox_id}")
            if row["status"] == "submitted" and row["external_ref"] == external_ref:
                return dict(row)
            if row["status"] != "submitting":
                raise LedgerConflict(f"outbox cannot be submitted from {row['status']}")
            now = _now()
            connection.execute(
                """
                UPDATE outbox
                SET status = 'submitted', external_ref = ?, next_attempt_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (external_ref, now, outbox_id),
            )
            connection.execute(
                """
                UPDATE attempts
                SET external_ref = ?,
                    status = CASE WHEN status = 'unknown' THEN status ELSE 'submitted' END,
                    version = version + 1,
                    updated_at = ?
                WHERE id = ? AND status != 'unknown'
                """,
                (external_ref, now, row["attempt_id"]),
            )
            self._event(
                connection,
                row["run_id"],
                "execution.submitted",
                {"attemptId": row["attempt_id"], "externalRef": external_ref},
                scope_id=row["scope_id"],
                invocation_id=row["invocation_id"],
                attempt_id=row["attempt_id"],
            )
        return self._outbox_by_id(outbox_id)

    def resolve_unknown_submit(
        self,
        outbox_id: str,
        *,
        external_ref: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        if not external_ref.strip():
            raise LedgerConflict("external execution reference is required")
        if not isinstance(evidence, dict) or not evidence:
            raise LedgerConflict("unknown submit resolution requires evidence")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"outbox not found: {outbox_id}")
            if row["status"] == "submitted" and row["external_ref"] == external_ref:
                return dict(row)
            if row["status"] != "unknown":
                raise LedgerConflict(
                    f"unknown submit cannot be resolved from {row['status']}"
                )
            now = _now()
            connection.execute(
                """
                UPDATE outbox
                SET status = 'submitted', external_ref = ?, next_attempt_at = NULL,
                    last_error_json = NULL, updated_at = ?
                WHERE id = ?
                """,
                (external_ref, now, outbox_id),
            )
            attempt = self._require_attempt(connection, row["attempt_id"])
            if attempt["external_ref"] not in (None, external_ref):
                raise LedgerConflict("resolved external reference conflicts with attempt")
            connection.execute(
                """
                UPDATE attempts
                SET external_ref = ?, status = 'submitted',
                    version = version + 1, updated_at = ?
                WHERE id = ?
                """,
                (external_ref, now, row["attempt_id"]),
            )
            invocation = self._require_invocation(connection, row["invocation_id"])
            if invocation["status"] == "reconciling":
                connection.execute(
                    """
                    UPDATE invocations
                    SET status = 'running', version = version + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, invocation["id"]),
                )
            run = self._require_run(connection, row["run_id"])
            if run["status"] == "blocked" and run["control_mode"] != "cancel":
                connection.execute(
                    """
                    UPDATE runs
                    SET status = 'running', error_json = NULL, version = version + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, run["id"]),
                )
            self._event(
                connection,
                row["run_id"],
                "execution.submit_reconciled",
                {
                    "attemptId": row["attempt_id"],
                    "externalRef": external_ref,
                    "evidence": evidence,
                },
                scope_id=row["scope_id"],
                invocation_id=row["invocation_id"],
                attempt_id=row["attempt_id"],
            )
        return self._outbox_by_id(outbox_id)

    def mark_submit_outbox_unknown(
        self,
        outbox_id: str,
        *,
        error: dict[str, Any],
    ) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"outbox not found: {outbox_id}")
            now = _now()
            connection.execute(
                """
                UPDATE outbox
                SET status = 'unknown', last_error_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json(error), now, outbox_id),
            )
            attempt = self._require_attempt(connection, row["attempt_id"])
            if attempt["status"] not in {"succeeded", "failed", "cancelled"}:
                connection.execute(
                    """
                    UPDATE attempts
                    SET status = 'unknown', error_json = ?, version = version + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (_json(error), now, row["attempt_id"]),
                )
                invocation = self._require_invocation(connection, row["invocation_id"])
                connection.execute(
                    """
                    UPDATE invocations
                    SET status = 'reconciling', error_json = ?, version = version + 1,
                        updated_at = ?
                    WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')
                    """,
                    (_json(error), now, invocation["id"]),
                )
                run = self._require_run(connection, row["run_id"])
                if run["status"] not in {"succeeded", "failed", "cancelled"}:
                    connection.execute(
                        """
                        UPDATE runs
                        SET status = 'blocked', error_json = ?, version = version + 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (_json(error), now, run["id"]),
                    )
            self._event(
                connection,
                row["run_id"],
                "execution.submit_unknown",
                {"attemptId": row["attempt_id"], "error": error},
                scope_id=row["scope_id"],
                invocation_id=row["invocation_id"],
                attempt_id=row["attempt_id"],
            )
        return self._outbox_by_id(outbox_id)

    def mark_submit_outbox_retryable(self, outbox_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"outbox not found: {outbox_id}")
            updated = connection.execute(
                """
                UPDATE outbox
                SET status = 'pending', last_error_json = NULL, updated_at = ?
                WHERE id = ? AND status = 'unknown'
                """,
                (_now(), outbox_id),
            )
            if updated.rowcount != 1:
                if row["status"] != "pending":
                    raise LedgerConflict(
                        f"outbox is not safely retryable from {row['status']}"
                    )
            else:
                now = _now()
                attempt = self._require_attempt(connection, row["attempt_id"])
                if attempt["status"] == "unknown":
                    connection.execute(
                        """
                        UPDATE attempts
                        SET status = 'created', error_json = NULL,
                            version = version + 1, updated_at = ?
                        WHERE id = ?
                        """,
                        (now, row["attempt_id"]),
                    )
                    invocation = self._require_invocation(connection, row["invocation_id"])
                    if invocation["status"] == "reconciling":
                        connection.execute(
                            """
                            UPDATE invocations
                            SET status = 'running', error_json = NULL,
                                version = version + 1, updated_at = ?
                            WHERE id = ?
                            """,
                            (now, invocation["id"]),
                        )
                    run = self._require_run(connection, row["run_id"])
                    if run["status"] == "blocked" and run["control_mode"] != "cancel":
                        connection.execute(
                            """
                            UPDATE runs
                            SET status = 'running', error_json = NULL,
                                version = version + 1, updated_at = ?
                            WHERE id = ?
                            """,
                            (now, run["id"]),
                        )
        return self._outbox_by_id(outbox_id)

    def _outbox_by_id(self, outbox_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM outbox WHERE id = ?", (outbox_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"outbox not found: {outbox_id}")
        return dict(row)

    def ensure_external_observation_wait(
        self,
        *,
        attempt_id: str,
        external_ref: str,
        not_before: str | None = None,
    ) -> dict[str, Any]:
        attempt = self.get_attempt(attempt_id)
        if attempt is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        run = self.get_run(attempt["run_id"])
        if run is None:
            raise KeyError(f"run not found: {attempt['run_id']}")
        wait_key = f"external-observe:{attempt_id}"
        now = not_before or _now()
        payload = {
            "attemptId": attempt_id,
            "runId": attempt["run_id"],
            "scopeId": attempt["scope_id"],
            "invocationId": attempt["invocation_id"],
            "externalRef": external_ref,
        }
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM waits WHERE namespace = ? AND wait_key = ?
                """,
                (run["namespace"], wait_key),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                        not_before, payload_json, status, worker_id, claimed_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'external-observe', ?, ?, ?, ?, ?, 'pending',
                              NULL, NULL, ?, ?)
                    """,
                    (
                        _new_id("wait"),
                        run["namespace"],
                        wait_key,
                        attempt["run_id"],
                        attempt["scope_id"],
                        attempt["invocation_id"],
                        now,
                        _json(payload),
                        _now(),
                        _now(),
                    ),
                )
            elif existing["status"] in {"completed", "cancelled"}:
                connection.execute(
                    """
                    UPDATE waits SET not_before = ?, payload_json = ?, status = 'pending',
                        worker_id = NULL, claimed_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, _json(payload), _now(), existing["id"]),
                )
        wait = self.get_wait_by_key(run["namespace"], wait_key)
        if wait is None:
            raise LedgerConflict("external observation wait disappeared")
        return wait

    def reschedule_wait(self, wait_id: str, *, not_before: str) -> dict[str, Any]:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE waits
                SET status = 'pending', worker_id = NULL, claimed_at = NULL,
                    not_before = ?, updated_at = ?
                WHERE id = ? AND status = 'claimed'
                """,
                (not_before, _now(), wait_id),
            )
            if updated.rowcount != 1:
                row = connection.execute(
                    "SELECT status FROM waits WHERE id = ?", (wait_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"wait not found: {wait_id}")
                if row["status"] != "pending":
                    raise LedgerConflict(f"wait cannot be rescheduled from {row['status']}")
        return self.get_wait(wait_id)  # type: ignore[return-value]

    def record_external_observation(
        self,
        attempt_id: str,
        *,
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        required = {
            "executionRef",
            "revision",
            "status",
            "observedAt",
            "executionFinal",
            "effectState",
        }
        if not required.issubset(observation):
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: observation is missing required fields"
            )
        revision = observation.get("revision")
        if not isinstance(revision, int) or revision < 1:
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: observation revision must be positive"
            )
        if not isinstance(observation.get("executionRef"), str):
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: executionRef must be a string"
            )
        if observation.get("status") not in {
            "accepted",
            "running",
            "waiting",
            "succeeded",
            "failed",
            "cancelled",
            "unknown",
        }:
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: observation status is invalid"
            )
        if not isinstance(observation.get("observedAt"), str):
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: observedAt must be a string"
            )
        if not isinstance(observation.get("executionFinal"), bool):
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: executionFinal must be boolean"
            )
        if observation.get("effectState") not in {
            "none",
            "possible",
            "confirmed",
            "not_applicable",
        }:
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: effectState is invalid"
            )
        if (
            observation.get("status") == "succeeded"
            and observation.get("executionFinal") is not True
        ):
            raise LedgerConflict(
                "EXECUTOR_PROTOCOL_VIOLATION: succeeded observation must be final"
            )
        with self._transaction() as connection:
            row = self._require_attempt(connection, attempt_id)
            if row["external_ref"] not in (None, observation["executionRef"]):
                raise LedgerConflict(
                    "EXECUTOR_PROTOCOL_VIOLATION: executionRef does not match attempt"
                )
            previous = row["observation_revision"]
            if previous is not None and revision < int(previous):
                raise LedgerConflict(
                    "EXECUTOR_PROTOCOL_VIOLATION: observation revision moved backwards"
                )
            observation_json = _json(observation)
            if previous is not None and revision == int(previous):
                if row["observation_json"] == observation_json:
                    return dict(row)
                raise LedgerConflict(
                    "EXECUTOR_PROTOCOL_VIOLATION: same observation revision changed"
                )
            if row["observation_json"] is not None:
                previous_observation = json.loads(row["observation_json"])
                previous_status = previous_observation.get("status")
                if previous_status in {"succeeded", "failed", "cancelled"}:
                    if previous_status != observation.get("status"):
                        raise LedgerConflict(
                            "EXECUTOR_PROTOCOL_VIOLATION: terminal observation changed"
                        )
                if (
                    previous_observation.get("executionFinal") is True
                    and observation.get("executionFinal") is not True
                ):
                    raise LedgerConflict(
                        "EXECUTOR_PROTOCOL_VIOLATION: final observation became non-final"
                    )
            if (
                observation.get("executionFinal") is True
                and observation.get("status")
                not in {"succeeded", "failed", "cancelled", "unknown"}
            ):
                raise LedgerConflict(
                    "EXECUTOR_PROTOCOL_VIOLATION: non-terminal observation is final"
                )
            connection.execute(
                """
                UPDATE attempts
                SET observation_revision = ?, observation_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (revision, observation_json, _now(), attempt_id),
            )
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

    def get_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return _row(row)

    def latest_attempt(self, invocation_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT * FROM attempts
            WHERE invocation_id = ?
            ORDER BY attempt_no DESC
            LIMIT 1
            """,
            (invocation_id,),
        ).fetchone()
        return _row(row)

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        output: Any = None,
        error: Any = None,
        external_ref: str | None = None,
    ) -> dict[str, Any]:
        with self._transaction() as connection:
            row = self._require_attempt(connection, attempt_id)
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                raise LedgerConflict(f"attempt is terminal: {row['status']}")
            if row["status"] == status:
                return dict(row)
            if row["status"] == "unknown" and status != "unknown":
                raise LedgerConflict(
                    "unknown attempt requires reconciliation before a terminal update"
                )
            if status == "unknown":
                invocation = self._require_invocation(connection, row["invocation_id"])
                run = self._require_run(connection, row["run_id"])
            connection.execute(
                """
                UPDATE attempts
                SET status = ?, output_json = ?, error_json = ?,
                    external_ref = ?, version = version + 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    _json_or_none(output),
                    _json_or_none(error),
                    external_ref,
                    _now(),
                    attempt_id,
                ),
            )
            self._event(
                connection,
                row["run_id"],
                "attempt.updated",
                {
                    "attemptId": attempt_id,
                    "status": status,
                    "version": int(row["version"]) + 1,
                },
                scope_id=row["scope_id"],
                invocation_id=row["invocation_id"],
                attempt_id=attempt_id,
            )
            if status == "unknown":
                invocation_version = int(invocation["version"]) + 1
                connection.execute(
                    """
                    UPDATE invocations
                    SET status = 'reconciling', version = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (invocation_version, _now(), invocation["id"]),
                )
                self._event(
                    connection,
                    row["run_id"],
                    "invocation.updated",
                    {
                        "invocationId": invocation["id"],
                        "status": "reconciling",
                        "version": invocation_version,
                    },
                    scope_id=row["scope_id"],
                    invocation_id=invocation["id"],
                )
                if run["status"] not in {
                    "succeeded",
                    "failed",
                    "cancelled",
                    "blocked",
                }:
                    run_version = int(run["version"]) + 1
                    connection.execute(
                        """
                        UPDATE runs
                        SET status = 'blocked', version = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (run_version, _now(), run["id"]),
                    )
                    self._event(
                        connection,
                        run["id"],
                        "run.updated",
                        {
                            "status": "blocked",
                            "controlMode": run["control_mode"],
                            "currentScopeId": run["current_scope_id"],
                            "currentNodeId": run["current_node_id"],
                            "currentInvocationId": run["current_invocation_id"],
                            "version": run_version,
                            "reason": "unresolved attempt result",
                        },
                    )
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

    def schedule_retry(
        self,
        attempt_id: str,
        *,
        current_node_id: str,
        next_attempt_at: str,
        error: dict[str, Any],
        delay_seconds: float,
    ) -> dict[str, Any]:
        envelope = error_output(error)
        with self._transaction() as connection:
            attempt = self._require_attempt(connection, attempt_id)
            if attempt["status"] in {"succeeded", "cancelled"}:
                raise LedgerConflict(f"attempt is terminal: {attempt['status']}")
            invocation = self._require_invocation(connection, attempt["invocation_id"])
            run = self._require_run(connection, attempt["run_id"])
            attempt_version = int(attempt["version"]) + 1
            invocation_version = int(invocation["version"]) + 1
            run_version = int(run["version"]) + 1
            now = _now()
            connection.execute(
                """
                UPDATE attempts
                SET status = 'failed', output_json = ?, error_json = ?,
                    next_attempt_at = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _json(envelope),
                    _json(error),
                    next_attempt_at,
                    attempt_version,
                    now,
                    attempt_id,
                ),
            )
            self._event(
                connection,
                run["id"],
                "attempt.updated",
                {
                    "attemptId": attempt_id,
                    "status": "failed",
                    "version": attempt_version,
                    "nextAttemptAt": next_attempt_at,
                },
                scope_id=attempt["scope_id"],
                invocation_id=attempt["invocation_id"],
                attempt_id=attempt_id,
            )
            connection.execute(
                """
                UPDATE invocations
                SET status = 'retry_wait', error_json = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json(error), invocation_version, now, invocation["id"]),
            )
            self._event(
                connection,
                run["id"],
                "invocation.updated",
                {
                    "invocationId": invocation["id"],
                    "status": "retry_wait",
                    "version": invocation_version,
                },
                scope_id=invocation["scope_id"],
                invocation_id=invocation["id"],
            )
            connection.execute(
                """
                UPDATE runs
                SET status = 'retry_wait', current_scope_id = ?,
                    current_node_id = ?, current_invocation_id = ?,
                    next_attempt_at = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    attempt["scope_id"],
                    current_node_id,
                    invocation["id"],
                    next_attempt_at,
                    run_version,
                    now,
                    run["id"],
                ),
            )
            self._event(
                connection,
                run["id"],
                "run.updated",
                {
                    "status": "retry_wait",
                    "controlMode": run["control_mode"],
                    "currentScopeId": attempt["scope_id"],
                    "currentNodeId": current_node_id,
                    "currentInvocationId": invocation["id"],
                    "nextAttemptAt": next_attempt_at,
                    "version": run_version,
                },
            )
            self._event(
                connection,
                run["id"],
                "retry.scheduled",
                {
                    "nodeId": current_node_id,
                    "invocationId": invocation["id"],
                    "attemptId": attempt_id,
                    "attemptNo": attempt["attempt_no"],
                    "nextAttemptAt": next_attempt_at,
                    "delaySeconds": delay_seconds,
                    "errorCode": error.get("code"),
                },
                scope_id=attempt["scope_id"],
                invocation_id=attempt["invocation_id"],
                attempt_id=attempt_id,
            )
            connection.execute(
                """
                INSERT INTO waits (
                    id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                    not_before, payload_json, status, worker_id, claimed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'retry', ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (
                    _new_id("wait"),
                    run["namespace"],
                    f"retry:{run['id']}:{attempt_id}",
                    run["id"],
                    attempt["scope_id"],
                    invocation["id"],
                    next_attempt_at,
                    _json(
                        {
                            "runId": run["id"],
                            "scopeId": attempt["scope_id"],
                            "nodeId": current_node_id,
                            "invocationId": invocation["id"],
                            "attemptId": attempt_id,
                        }
                    ),
                    now,
                    now,
                ),
            )
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

    def reconcile_attempt(
        self,
        attempt_id: str,
        *,
        expected_version: int,
        conclusion: Literal[
            "confirmed_succeeded",
            "confirmed_failed",
            "confirmed_cancelled",
            "confirmed_not_started",
        ],
        evidence_refs: list[str],
        reason: str,
        actor: str,
        output: Any = None,
        enqueue_wait: bool = False,
    ) -> dict[str, Any]:
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise LedgerConflict("reconciliation requires evidence references")
        if not reason.strip() or not actor.strip():
            raise LedgerConflict("reconciliation reason and actor are required")
        if conclusion == "confirmed_succeeded" and output is None:
            raise LedgerConflict("confirmed_succeeded requires output")
        status_by_conclusion = {
            "confirmed_succeeded": "succeeded",
            "confirmed_failed": "failed",
            "confirmed_cancelled": "cancelled",
            "confirmed_not_started": "cancelled",
        }
        status = status_by_conclusion[conclusion]
        reconciliation = {
            "conclusion": conclusion,
            "evidenceRefs": evidence_refs,
            "reason": reason,
            "actor": actor,
        }
        error = None
        stored_output = output
        if conclusion == "confirmed_failed":
            error = {"code": "RECONCILED_FAILURE", "message": reason}
            stored_output = error_output(error)
        elif conclusion == "confirmed_cancelled":
            error = {"code": "RECONCILED_CANCELLED", "message": reason}
            stored_output = error_output(error)
        elif conclusion == "confirmed_not_started":
            error = {"code": "RECONCILED_NOT_STARTED", "message": reason}
            stored_output = error_output(error)
        with self._transaction() as connection:
            row = self._require_attempt(connection, attempt_id)
            if int(row["version"]) != expected_version:
                raise LedgerConflict("attempt version conflict")
            if row["status"] != "unknown":
                raise LedgerConflict(
                    f"only an unknown attempt can be reconciled: {row['status']}"
                )
            version = int(row["version"]) + 1
            connection.execute(
                """
                UPDATE attempts
                SET status = ?, output_json = ?, error_json = ?,
                    reconciliation_json = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    _json_or_none(stored_output),
                    _json_or_none(error),
                    json.dumps(
                        reconciliation,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    version,
                    _now(),
                    attempt_id,
                ),
            )
            self._event(
                connection,
                row["run_id"],
                "attempt.reconciled",
                {
                    "attemptId": attempt_id,
                    "conclusion": conclusion,
                    "status": status,
                    "version": version,
                    "evidenceRefs": evidence_refs,
                    "reason": reason,
                    "actor": actor,
                },
                scope_id=row["scope_id"],
                invocation_id=row["invocation_id"],
                attempt_id=attempt_id,
            )
            if enqueue_wait:
                run = self._require_run(connection, row["run_id"])
                now = _now()
                wait_key = f"attempt-reconcile:{attempt_id}"
                existing_wait = connection.execute(
                    """
                    SELECT status FROM waits
                    WHERE namespace = ? AND wait_key = ?
                    """,
                    (run["namespace"], wait_key),
                ).fetchone()
                if existing_wait is None:
                    connection.execute(
                        """
                        INSERT INTO waits (
                            id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                            not_before, payload_json, status, worker_id, claimed_at,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, 'attempt-reconcile', ?, ?, ?, ?, ?, 'pending',
                                  NULL, NULL, ?, ?)
                        """,
                        (
                            _new_id("wait"),
                            run["namespace"],
                            wait_key,
                            row["run_id"],
                            row["scope_id"],
                            row["invocation_id"],
                            now,
                            _json(
                                {
                                    "attemptId": attempt_id,
                                    "runId": row["run_id"],
                                    "scopeId": row["scope_id"],
                                    "invocationId": row["invocation_id"],
                                    "attemptVersion": version,
                                }
                            ),
                            now,
                            now,
                        ),
                    )
                elif existing_wait["status"] == "cancelled":
                    connection.execute(
                        """
                        UPDATE waits
                        SET kind = 'attempt-reconcile', not_before = ?,
                            payload_json = ?, status = 'pending',
                            worker_id = NULL, claimed_at = NULL, updated_at = ?
                        WHERE namespace = ? AND wait_key = ?
                        """,
                        (
                            now,
                            _json(
                                {
                                    "attemptId": attempt_id,
                                    "runId": row["run_id"],
                                    "scopeId": row["scope_id"],
                                    "invocationId": row["invocation_id"],
                                    "attemptVersion": version,
                                }
                            ),
                            now,
                            run["namespace"],
                            wait_key,
                        ),
                    )
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

    def ensure_attempt_reconciliation_wait(self, attempt_id: str) -> dict[str, Any]:
        """Ensure a persisted reconciliation fact has a recoverable wake."""
        with self._transaction() as connection:
            attempt = self._require_attempt(connection, attempt_id)
            if attempt["reconciliation_json"] is None or attempt["status"] == "unknown":
                raise LedgerConflict("attempt reconciliation is not committed")
            run = self._require_run(connection, attempt["run_id"])
            now = _now()
            wait_key = f"attempt-reconcile:{attempt_id}"
            existing = connection.execute(
                """
                SELECT * FROM waits
                WHERE namespace = ? AND wait_key = ?
                """,
                (run["namespace"], wait_key),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO waits (
                        id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                        not_before, payload_json, status, worker_id, claimed_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'attempt-reconcile', ?, ?, ?, ?, ?, 'pending',
                              NULL, NULL, ?, ?)
                    """,
                    (
                        _new_id("wait"),
                        run["namespace"],
                        wait_key,
                        attempt["run_id"],
                        attempt["scope_id"],
                        attempt["invocation_id"],
                        now,
                        _json(
                            {
                                "attemptId": attempt_id,
                                "runId": attempt["run_id"],
                                "scopeId": attempt["scope_id"],
                                "invocationId": attempt["invocation_id"],
                                "attemptVersion": attempt["version"],
                            }
                        ),
                        now,
                        now,
                    ),
                )
            elif existing["status"] == "cancelled":
                connection.execute(
                    """
                    UPDATE waits
                    SET kind = 'attempt-reconcile', not_before = ?, status = 'pending',
                        worker_id = NULL, claimed_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, existing["id"]),
                )
        wait = self.get_wait_by_key(str(run["namespace"]), wait_key)
        if wait is None:
            raise LedgerConflict("attempt reconciliation wait is missing")
        return wait

    def create_human_request(
        self,
        *,
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
        request_id = _new_id("human")
        input_json = _json(input_value)
        with self._transaction() as connection:
            self._require_scope(connection, run_id, scope_id)
            connection.execute(
                """
                INSERT INTO human_requests (
                    id, run_id, scope_id, invocation_id, request_type, title,
                    instructions, input_json, input_digest, subject_digest,
                    choices_json, decision_schema_json, authorized_subjects_json,
                    created_at, expires_at, version, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'pending')
                """,
                (
                    request_id,
                    run_id,
                    scope_id,
                    invocation_id,
                    request_type,
                    title,
                    instructions,
                    input_json,
                    _digest(input_json),
                    subject_digest,
                    _json(choices),
                    _json(decision_schema),
                    _json(authorized_subjects),
                    _now(),
                    expires_at,
                ),
            )
            self._event(
                connection,
                run_id,
                "human.created",
                {"requestId": request_id, "status": "pending"},
                scope_id=scope_id,
                invocation_id=invocation_id,
            )
            run = self._require_run(connection, run_id)
            now = _now()
            connection.execute(
                """
                INSERT INTO waits (
                    id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                    not_before, payload_json, status, worker_id, claimed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'human', ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (
                    _new_id("wait"),
                    run["namespace"],
                    f"human:{request_id}",
                    run_id,
                    scope_id,
                    invocation_id,
                    expires_at,
                    _json({"requestId": request_id}),
                    now,
                    now,
                ),
            )
        return self.get_human_request(request_id)  # type: ignore[return-value]

    def get_human_request(self, request_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM human_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return _row(row)

    def list_human_requests(
        self,
        *,
        run_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM human_requests WHERE 1 = 1"
        parameters: list[str] = []
        if run_id is not None:
            query += " AND run_id = ?"
            parameters.append(run_id)
        if status is not None:
            query += " AND status = ?"
            parameters.append(status)
        query += " ORDER BY created_at"
        rows = self._connection.execute(query, parameters).fetchall()
        return [request for row in rows if (request := _row(row)) is not None]

    def get_human_decision(self, request_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM human_decisions WHERE request_id = ?", (request_id,)
        ).fetchone()
        return _row(row)

    def get_human_decision_by_idempotency_key(
        self, idempotency_key: str
    ) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM human_decisions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return _row(row)

    def get_human_progress_intent(self, request_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT * FROM human_progress_intents
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
        return _row(row)

    def ensure_human_progress_intent(self, request_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM human_progress_intents
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            request = self._require_human_request(connection, request_id)
            decision = connection.execute(
                """
                SELECT id FROM human_decisions
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if decision is None:
                raise LedgerConflict("human decision is missing")
            now = _now()
            intent_id = _new_id("intent")
            connection.execute(
                """
                INSERT INTO human_progress_intents (
                    id, request_id, run_id, scope_id, invocation_id, decision_id,
                    action, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'resume-human-decision', 'pending', ?, ?)
                """,
                (
                    intent_id,
                    request_id,
                    request["run_id"],
                    request["scope_id"],
                    request["invocation_id"],
                    decision["id"],
                    now,
                    now,
                ),
            )
            return dict(
                connection.execute(
                    """
                    SELECT * FROM human_progress_intents
                    WHERE id = ?
                    """,
                    (intent_id,),
                ).fetchone()
            )

    def complete_human_progress_intent(self, request_id: str) -> None:
        with self._transaction() as connection:
            intent = connection.execute(
                """
                SELECT run_id FROM human_progress_intents
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE human_progress_intents
                SET status = 'completed', updated_at = ?
                WHERE request_id = ? AND status = 'pending'
                """,
                (_now(), request_id),
            )
            if intent is not None:
                connection.execute(
                    """
                    UPDATE waits
                    SET status = 'completed', updated_at = ?
                    WHERE run_id = ? AND wait_key = ? AND status IN ('pending', 'claimed')
                    """,
                    (_now(), intent["run_id"], f"human-progress:{request_id}"),
                )

    def register_artifact(
        self,
        *,
        run_id: str,
        source_path: Path,
        name: str,
        media_type: str,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        source = source_path.expanduser().resolve()
        if not source.is_file():
            raise LedgerConflict(f"artifact source is not a file: {source_path}")
        return self.register_artifact_content(
            run_id=run_id,
            content=source.read_bytes(),
            name=name,
            media_type=media_type,
            invocation_id=invocation_id,
        )

    def register_artifact_content(
        self,
        *,
        run_id: str,
        content: bytes,
        name: str,
        media_type: str,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        if invocation_id is not None:
            invocation = self.get_invocation(invocation_id)
            if invocation is None or invocation["run_id"] != run_id:
                raise LedgerConflict("artifact invocation is not part of run")
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        artifact_id = _new_id("artifact")
        destination = self._artifact_root / artifact_id
        destination.write_bytes(content)
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            connection.execute(
                """
                INSERT INTO artifacts (
                    id, namespace, run_id, invocation_id, name, media_type,
                    size_bytes, digest, storage_ref, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)
                """,
                (
                    artifact_id,
                    run["namespace"],
                    run_id,
                    invocation_id,
                    name,
                    media_type,
                    len(content),
                    digest,
                    str(destination),
                    _now(),
                ),
            )
            self._event(
                connection,
                run_id,
                "artifact.created",
                {"artifactId": artifact_id, "digest": digest, "status": "ready"},
                invocation_id=invocation_id,
            )
        return self.get_artifact(artifact_id)  # type: ignore[return-value]

    def register_external_artifacts(
        self,
        *,
        attempt_id: str,
        execution_ref: str,
        artifacts: list[tuple[dict[str, Any], bytes]],
    ) -> list[str]:
        """Import a verified batch atomically, deduplicated by immutable source identity.

        Files are durable before any ready row becomes visible. A crash before the
        transaction commits can leave unreferenced files, never a partial ready row.
        """
        attempt = self.get_attempt(attempt_id)
        if attempt is None or attempt["external_ref"] != execution_ref:
            raise LedgerConflict("artifact source does not match attempt")
        run = self.get_run(attempt["run_id"])
        invocation = self.get_invocation(attempt["invocation_id"])
        if (
            run is None
            or invocation is None
            or invocation["run_id"] != run["id"]
            or invocation["scope_id"] != attempt["scope_id"]
        ):
            raise LedgerConflict("artifact attempt ownership is invalid")
        metadata = [item for item, _ in artifacts]
        validate_artifact_metadata(metadata, execution_ref, run["namespace"])
        observation = json.loads(attempt["observation_json"] or "null")
        if (
            not isinstance(observation, dict)
            or observation.get("status") != "succeeded"
            or observation.get("executionFinal") is not True
            or observation.get("executionRef") != execution_ref
            or observation.get("artifacts") != metadata
        ):
            raise LedgerConflict("artifact source differs from persisted observation")
        for item, content in artifacts:
            validate_artifact_content(item, content)
        refs = []
        with self._transaction() as connection:
            current = self._require_attempt(connection, attempt_id)
            if (
                current["external_ref"] != execution_ref
                or current["observation_json"] != attempt["observation_json"]
            ):
                raise LedgerConflict("artifact source changed during import")
            for item, content in artifacts:
                source_key = (attempt_id, execution_ref, item["artifactId"], item["version"])
                existing = connection.execute(
                    "SELECT * FROM external_artifact_sources WHERE attempt_id = ? "
                    "AND execution_ref = ? AND source_artifact_id = ? AND version = ?",
                    source_key,
                ).fetchone()
                if existing is not None:
                    if existing["metadata_json"] != _json(item):
                        raise LedgerConflict("artifact source metadata conflict")
                    self.validate_artifact_refs(run["id"], [existing["artifact_id"]])
                    refs.append(existing["artifact_id"])
                    continue
                artifact_id = _new_id("artifact")
                destination = self._artifact_root / artifact_id
                with destination.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                directory_fd = os.open(self._artifact_root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                connection.execute(
                    "INSERT INTO artifacts (id, namespace, run_id, invocation_id, name, "
                    "media_type, size_bytes, digest, storage_ref, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)",
                    (
                        artifact_id,
                        run["namespace"],
                        run["id"],
                        invocation["id"],
                        item["name"],
                        item["mediaType"],
                        item["sizeBytes"],
                        item["digest"],
                        str(destination),
                        _now(),
                    ),
                )
                connection.execute(
                    "INSERT INTO external_artifact_sources (attempt_id, execution_ref, "
                    "source_artifact_id, version, metadata_json, artifact_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (*source_key, _json(item), artifact_id),
                )
                self._event(
                    connection,
                    run["id"],
                    "artifact.created",
                    {"artifactId": artifact_id, "digest": item["digest"], "status": "ready"},
                    invocation_id=invocation["id"],
                    attempt_id=attempt_id,
                )
                refs.append(artifact_id)
        return refs

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        return _row(row)

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at, id",
            (run_id,),
        ).fetchall()
        return [artifact for row in rows if (artifact := _row(row)) is not None]

    def validate_artifact_refs(self, run_id: str, artifact_refs: list[str]) -> None:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        for artifact_id in artifact_refs:
            artifact = self.get_artifact(artifact_id)
            if artifact is None or artifact["status"] != "ready":
                raise LedgerConflict(f"artifact is not ready: {artifact_id}")
            if artifact["run_id"] != run_id or artifact["namespace"] != run["namespace"]:
                raise LedgerConflict(f"artifact is not authorized for run: {artifact_id}")
            storage_ref = Path(artifact["storage_ref"])
            if not storage_ref.is_file():
                raise LedgerConflict(f"artifact content is unavailable: {artifact_id}")
            content = storage_ref.read_bytes()
            digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
            if digest != artifact["digest"]:
                raise LedgerConflict(f"artifact digest mismatch: {artifact_id}")

    def record_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        scope_id: str | None = None,
        invocation_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            self._event(
                connection,
                run_id,
                event_type,
                payload,
                scope_id=scope_id,
                invocation_id=invocation_id,
                attempt_id=attempt_id,
            )

    def create_wait(
        self,
        *,
        namespace: str,
        wait_key: str,
        kind: str,
        run_id: str,
        not_before: str,
        payload: dict[str, Any],
        scope_id: str | None = None,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        if not wait_key.strip() or not kind.strip():
            raise LedgerConflict("wait key and kind are required")
        wait_id = _new_id("wait")
        now = _now()
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            connection.execute(
                """
                INSERT INTO waits (
                    id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                    not_before, payload_json, status, worker_id, claimed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (
                    wait_id,
                    namespace,
                    wait_key,
                    kind,
                    run_id,
                    scope_id,
                    invocation_id,
                    not_before,
                    _json(payload),
                    now,
                    now,
                ),
            )
        return self.get_wait(wait_id)  # type: ignore[return-value]

    def get_wait(self, wait_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM waits WHERE id = ?", (wait_id,)
        ).fetchone()
        return _row(row)

    def get_wait_by_key(self, namespace: str, wait_key: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT * FROM waits
            WHERE namespace = ? AND wait_key = ?
            """,
            (namespace, wait_key),
        ).fetchone()
        return _row(row)

    def list_waits(
        self,
        *,
        run_id: str | None = None,
        kind: str | None = None,
        statuses: tuple[str, ...] = ("pending", "claimed"),
    ) -> list[dict[str, Any]]:
        if not statuses:
            return []
        clauses = [f"status IN ({','.join('?' for _ in statuses)})"]
        parameters: list[Any] = list(statuses)
        if run_id is not None:
            clauses.append("run_id = ?")
            parameters.append(run_id)
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(kind)
        rows = self._connection.execute(
            f"""
            SELECT * FROM waits
            WHERE {' AND '.join(clauses)}
            ORDER BY not_before, created_at, id
            """,
            parameters,
        ).fetchall()
        return [wait for row in rows if (wait := _row(row)) is not None]

    def update_wait(self, wait_id: str, *, not_before: str) -> dict[str, Any]:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE waits
                SET not_before = ?, updated_at = ?
                WHERE id = ?
                """,
                (not_before, _now(), wait_id),
            )
            if updated.rowcount != 1:
                raise KeyError(f"wait not found: {wait_id}")
        return self.get_wait(wait_id)  # type: ignore[return-value]

    def list_due_waits(
        self,
        *,
        now: str,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        clauses = ["status = 'pending'", "not_before <= ?"]
        parameters: list[Any] = [now]
        if namespace is not None:
            clauses.append("namespace = ?")
            parameters.append(namespace)
        parameters.append(limit)
        rows = self._connection.execute(
            f"""
            SELECT * FROM waits
            WHERE {' AND '.join(clauses)}
            ORDER BY not_before, created_at, id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [wait for row in rows if (wait := _row(row)) is not None]

    def claim_wait(
        self,
        wait_id: str,
        *,
        worker_id: str,
        now: str,
    ) -> dict[str, Any] | None:
        if not worker_id.strip():
            raise LedgerConflict("worker id is required")
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE waits
                SET status = 'claimed', worker_id = ?, claimed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'pending' AND not_before <= ?
                """,
                (worker_id, now, now, wait_id, now),
            )
            if updated.rowcount != 1:
                return None
        return self.get_wait(wait_id)

    def complete_wait(self, wait_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM waits WHERE id = ?", (wait_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"wait not found: {wait_id}")
            if row["status"] in {"completed", "cancelled"}:
                return dict(row)
            if row["status"] != "claimed":
                raise LedgerConflict(f"wait is not claimed: {row['status']}")
            connection.execute(
                """
                UPDATE waits
                SET status = 'completed', updated_at = ?
                WHERE id = ?
                """,
                (_now(), wait_id),
            )
        return self.get_wait(wait_id)  # type: ignore[return-value]

    def release_wait(self, wait_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE waits
                SET status = 'pending', worker_id = NULL, claimed_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'claimed'
                """,
                (_now(), wait_id),
            )
            if updated.rowcount != 1:
                row = connection.execute(
                    "SELECT * FROM waits WHERE id = ?", (wait_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"wait not found: {wait_id}")
        return self.get_wait(wait_id)  # type: ignore[return-value]

    def requeue_stale_waits(
        self,
        *,
        now: str,
        older_than: str,
        namespace: str | None = None,
    ) -> int:
        clauses = [
            "status = 'claimed'",
            "claimed_at IS NOT NULL",
            "claimed_at <= ?",
        ]
        parameters: list[Any] = [older_than]
        if namespace is not None:
            clauses.append("namespace = ?")
            parameters.append(namespace)
        with self._transaction() as connection:
            updated = connection.execute(
                f"""
                UPDATE waits
                SET status = 'pending', worker_id = NULL, claimed_at = NULL, updated_at = ?
                WHERE {' AND '.join(clauses)}
                """,
                [now, *parameters],
            )
            return updated.rowcount

    def decide_human_request(
        self,
        request_id: str,
        *,
        choice: str | None = None,
        decision: Any | None = None,
        comment: str = "",
        expected_version: int,
        subject_digest: str,
        actor: str,
        idempotency_key: str,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        with self._transaction() as connection:
            previous = connection.execute(
                """
                SELECT request_id, request_version, choice, comment, actor
                FROM human_decisions WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
            if previous is not None:
                if previous["request_id"] != request_id:
                    raise LedgerConflict("idempotency key belongs to another request")
                return dict(self._require_human_request(connection, request_id))

            request = self._require_human_request(connection, request_id)
            if int(request["version"]) != expected_version:
                raise LedgerConflict("human request version conflict")
            if request["status"] != "pending":
                raise LedgerConflict("human request is not pending")
            if request["subject_digest"] != subject_digest:
                raise LedgerConflict("human request subject conflict")
            if actor not in json.loads(request["authorized_subjects_json"]):
                raise LedgerConflict("actor is not authorized")
            if request["request_type"] in {"approval", "review"}:
                if choice not in json.loads(request["choices_json"]):
                    raise LedgerConflict("choice is not allowed")
                stored_decision = {"decision": choice, "comment": comment}
            else:
                if decision is None:
                    raise LedgerConflict("input request requires a structured decision")
                choice = ""
                stored_decision = decision
            if request["expires_at"] <= _now():
                raise LedgerConflict("human request is expired")

            decision_id = _new_id("decision")
            version = int(request["version"]) + 1
            connection.execute(
                """
                INSERT INTO human_decisions (
                    id, request_id, request_version, choice, comment, decision_json,
                    actor, subject_digest, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    request_id,
                    version,
                    choice,
                    comment,
                    _json(stored_decision),
                    actor,
                    subject_digest,
                    idempotency_key,
                    _now(),
                ),
            )
            connection.execute(
                """
                UPDATE human_requests
                SET status = 'decided', version = ?, decision_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (version, decision_id, _now(), request_id),
            )
            self._event(
                connection,
                request["run_id"],
                "human.decided",
                {"requestId": request_id, "choice": choice, "version": version},
                scope_id=request["scope_id"],
                invocation_id=request["invocation_id"],
            )
            if command_id is not None:
                updated = connection.execute(
                    """
                    UPDATE commands
                    SET before_version = ?, after_version = ?, transition = ?, updated_at = ?
                    WHERE id = ? AND status = 'accepted'
                    """,
                    (
                        int(request["version"]),
                        version,
                        "human.decided",
                        _now(),
                        command_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise LedgerConflict("human decision command is not accepted")
            connection.execute(
                """
                UPDATE waits
                SET status = 'completed', updated_at = ?
                WHERE namespace = (
                    SELECT namespace FROM runs WHERE id = ?
                ) AND wait_key = ? AND status IN ('pending', 'claimed')
                """,
                (_now(), request["run_id"], f"human:{request_id}"),
            )
            now = _now()
            connection.execute(
                """
                INSERT INTO human_progress_intents (
                    id, request_id, run_id, scope_id, invocation_id, decision_id,
                    action, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'resume-human-decision', 'pending', ?, ?)
                """,
                (
                    _new_id("intent"),
                    request_id,
                    request["run_id"],
                    request["scope_id"],
                    request["invocation_id"],
                    decision_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO waits (
                    id, namespace, wait_key, kind, run_id, scope_id, invocation_id,
                    not_before, payload_json, status, worker_id, claimed_at,
                    created_at, updated_at
                )
                SELECT ?, r.namespace, ?, 'human-progress', r.id, ?, ?, ?, ?, 'pending',
                       NULL, NULL, ?, ?
                FROM runs AS r
                WHERE r.id = ?
                """,
                (
                    _new_id("wait"),
                    f"human-progress:{request_id}",
                    request["scope_id"],
                    request["invocation_id"],
                    now,
                    _json({"requestId": request_id}),
                    now,
                    now,
                    request["run_id"],
                ),
            )
            return dict(self._require_human_request(connection, request_id))

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        return [event for row in rows if (event := _row(row)) is not None]

    def list_events_after(
        self,
        run_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self._connection.execute(
            """
            SELECT * FROM run_events
            WHERE run_id = ? AND seq > ?
            ORDER BY seq
            LIMIT ?
            """,
            (run_id, after_seq, limit),
        ).fetchall()
        return [event for row in rows if (event := _row(row)) is not None]

    def get_event_cursor(self, run_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(seq), 0) AS cursor FROM run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["cursor"]) if row is not None else 0

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                deployment_id TEXT,
                workflow_id TEXT NOT NULL,
                package_digest TEXT NOT NULL,
                binding_digest TEXT,
                plan_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                control_mode TEXT NOT NULL,
                deadline_at TEXT NOT NULL,
                next_attempt_at TEXT,
                version INTEGER NOT NULL,
                current_node_id TEXT,
                current_scope_id TEXT REFERENCES scopes(id),
                current_invocation_id TEXT REFERENCES invocations(id),
                rerun_of TEXT REFERENCES runs(id),
                rerun_reason TEXT,
                output_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                operation TEXT NOT NULL,
                namespace TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT 'local-user',
                resource_id TEXT NOT NULL,
                status TEXT NOT NULL,
                resource_version INTEGER,
                before_version INTEGER,
                after_version INTEGER,
                transition TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scopes (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                parent_scope_id TEXT REFERENCES scopes(id),
                parent_invocation_id TEXT,
                workflow_id TEXT NOT NULL,
                path_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                output_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invocations (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT NOT NULL REFERENCES scopes(id),
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                output_json TEXT,
                error_json TEXT,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT NOT NULL REFERENCES scopes(id),
                invocation_id TEXT NOT NULL REFERENCES invocations(id),
                attempt_no INTEGER NOT NULL,
                status TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                dispatch_key TEXT NOT NULL UNIQUE,
                effect_key TEXT NOT NULL,
                output_json TEXT,
                error_json TEXT,
                external_ref TEXT,
                observation_revision INTEGER,
                observation_json TEXT,
                next_attempt_at TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                reconciliation_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(invocation_id, attempt_no)
            );
            CREATE TABLE IF NOT EXISTS human_requests (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT NOT NULL REFERENCES scopes(id),
                invocation_id TEXT NOT NULL REFERENCES invocations(id),
                request_type TEXT NOT NULL,
                title TEXT NOT NULL,
                instructions TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                subject_digest TEXT NOT NULL,
                choices_json TEXT NOT NULL,
                decision_schema_json TEXT NOT NULL,
                authorized_subjects_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                decision_id TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS human_decisions (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE REFERENCES human_requests(id),
                request_version INTEGER NOT NULL,
                choice TEXT NOT NULL,
                comment TEXT NOT NULL,
                decision_json TEXT NOT NULL DEFAULT '{}',
                actor TEXT NOT NULL,
                subject_digest TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS human_progress_intents (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE REFERENCES human_requests(id),
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT NOT NULL REFERENCES scopes(id),
                invocation_id TEXT NOT NULL REFERENCES invocations(id),
                decision_id TEXT NOT NULL UNIQUE REFERENCES human_decisions(id),
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS waits (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                wait_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT REFERENCES scopes(id),
                invocation_id TEXT REFERENCES invocations(id),
                not_before TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                worker_id TEXT,
                claimed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(namespace, wait_key)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                action_key TEXT NOT NULL UNIQUE,
                namespace TEXT NOT NULL,
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT NOT NULL REFERENCES scopes(id),
                invocation_id TEXT NOT NULL REFERENCES invocations(id),
                attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(id),
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                external_ref TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                last_error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                scope_id TEXT,
                invocation_id TEXT,
                attempt_id TEXT,
                seq INTEGER NOT NULL,
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                UNIQUE(run_id, seq)
            );
            CREATE TABLE IF NOT EXISTS external_artifact_sources (
                attempt_id TEXT NOT NULL REFERENCES attempts(id),
                execution_ref TEXT NOT NULL,
                source_artifact_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                artifact_id TEXT NOT NULL UNIQUE REFERENCES artifacts(id),
                PRIMARY KEY (attempt_id, execution_ref, source_artifact_id, version)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                run_id TEXT NOT NULL REFERENCES runs(id),
                invocation_id TEXT REFERENCES invocations(id),
                name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                digest TEXT NOT NULL,
                storage_ref TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        human_decision_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(human_decisions)").fetchall()
        }
        command_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(commands)").fetchall()
        }
        attempt_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(attempts)").fetchall()
        }
        for column, definition in (
            ("observation_revision", "INTEGER"),
            ("observation_json", "TEXT"),
        ):
            if column not in attempt_columns:
                self._connection.execute(
                    f"ALTER TABLE attempts ADD COLUMN {column} {definition}"
                )
        command_sql = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'commands'"
        ).fetchone()
        if "subject" not in command_columns:
            self._connection.execute(
                "ALTER TABLE commands ADD COLUMN subject TEXT NOT NULL DEFAULT 'local-user'"
            )
            command_columns.add("subject")
        if command_sql is not None and "idempotency_key TEXT NOT NULL UNIQUE" in (
            command_sql["sql"] or ""
        ):
            self._connection.executescript(
                """
                CREATE TABLE commands_migrated (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resource_version INTEGER,
                    before_version INTEGER,
                    after_version INTEGER,
                    transition TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO commands_migrated (
                    id, idempotency_key, fingerprint, operation, namespace,
                    subject, resource_id, status, resource_version, before_version,
                    after_version, transition, error_json, created_at, updated_at
                )
                SELECT id, idempotency_key, fingerprint, operation, namespace,
                       COALESCE(subject, 'local-user'), resource_id, status,
                       resource_version, NULL, NULL, NULL, error_json,
                       created_at, updated_at
                FROM commands;
                DROP TABLE commands;
                ALTER TABLE commands_migrated RENAME TO commands;
                """
            )
            command_columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(commands)").fetchall()
            }
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS commands_scope_key
            ON commands(namespace, subject, operation, idempotency_key)
            """
        )
        for column, definition in (
            ("before_version", "INTEGER"),
            ("after_version", "INTEGER"),
            ("transition", "TEXT"),
        ):
            if column not in command_columns:
                self._connection.execute(
                    f"ALTER TABLE commands ADD COLUMN {column} {definition}"
                )
        if "decision_json" not in human_decision_columns:
            self._connection.execute(
                "ALTER TABLE human_decisions ADD COLUMN decision_json TEXT NOT NULL DEFAULT '{}'"
            )
        run_columns = {
            row["name"] for row in self._connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        for column, definition in (
            ("deployment_id", "TEXT"),
            ("rerun_of", "TEXT"),
            ("rerun_reason", "TEXT"),
            ("next_attempt_at", "TEXT"),
            ("current_scope_id", "TEXT"),
            ("current_invocation_id", "TEXT"),
        ):
            if column not in run_columns:
                self._connection.execute(f"ALTER TABLE runs ADD COLUMN {column} {definition}")
        attempt_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(attempts)").fetchall()
        }
        for column, definition in (
            ("next_attempt_at", "TEXT"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("reconciliation_json", "TEXT"),
        ):
            if column not in attempt_columns:
                self._connection.execute(f"ALTER TABLE attempts ADD COLUMN {column} {definition}")
        scope_columns = {
            row["name"] for row in self._connection.execute("PRAGMA table_info(scopes)").fetchall()
        }
        for column, definition in (
            ("input_json", "TEXT"),
            ("input_digest", "TEXT"),
            ("output_json", "TEXT"),
            ("error_json", "TEXT"),
        ):
            if column not in scope_columns:
                self._connection.execute(f"ALTER TABLE scopes ADD COLUMN {column} {definition}")
        self._migrate_legacy_run_continuations()
        self._connection.commit()

    def _migrate_legacy_run_continuations(self) -> None:
        """Recover unambiguous active-run pointers from pre-continuation schemas."""
        active_statuses = (
            "queued",
            "running",
            "waiting",
            "paused",
            "stopping",
            "retry_wait",
        )
        placeholders = ", ".join("?" for _ in active_statuses)
        rows = self._connection.execute(
            f"""
            SELECT id, status, current_node_id, version
            FROM runs
            WHERE current_scope_id IS NULL
              AND current_node_id IS NOT NULL
              AND status IN ({placeholders})
            """,
            active_statuses,
        ).fetchall()
        for row in rows:
            run_id = str(row["id"])
            node_id = str(row["current_node_id"])
            scopes = self._connection.execute(
                """
                SELECT id
                FROM scopes
                WHERE run_id = ? AND status = 'active'
                ORDER BY created_at, id
                """,
                (run_id,),
            ).fetchall()
            if len(scopes) != 1:
                matching_scopes = self._connection.execute(
                    """
                    SELECT DISTINCT scope_id
                    FROM invocations
                    WHERE run_id = ? AND node_id = ?
                    """,
                    (run_id, node_id),
                ).fetchall()
                if len(matching_scopes) == 1:
                    scope_id = str(matching_scopes[0]["scope_id"])
                else:
                    self._block_legacy_continuation(
                        run_id,
                        int(row["version"]),
                        "multiple or missing active scopes",
                    )
                    continue
            else:
                scope_id = str(scopes[0]["id"])

            invocations = self._connection.execute(
                """
                SELECT id
                FROM invocations
                WHERE run_id = ? AND scope_id = ? AND node_id = ?
                ORDER BY created_at, id
                """,
                (run_id, scope_id, node_id),
            ).fetchall()
            if len(invocations) > 1:
                self._block_legacy_continuation(
                    run_id,
                    int(row["version"]),
                    "multiple invocations for the current node",
                )
                continue
            invocation_id = (
                str(invocations[0]["id"]) if invocations else None
            )
            now = _now()
            version = int(row["version"]) + 1
            self._connection.execute(
                """
                UPDATE runs
                SET current_scope_id = ?, current_invocation_id = ?,
                    version = ?, updated_at = ?
                WHERE id = ?
                """,
                (scope_id, invocation_id, version, now, run_id),
            )
            self._event(
                self._connection,
                run_id,
                "run.continuation.migrated",
                {
                    "currentScopeId": scope_id,
                    "currentNodeId": node_id,
                    "currentInvocationId": invocation_id,
                    "version": version,
                },
                scope_id=scope_id,
                invocation_id=invocation_id,
            )

    def _block_legacy_continuation(
        self,
        run_id: str,
        current_version: int,
        reason: str,
    ) -> None:
        now = _now()
        version = current_version + 1
        error = {
            "code": "CONTINUATION_MIGRATION_REQUIRED",
            "message": "Legacy run continuation cannot be recovered safely.",
            "details": {"reason": reason},
        }
        self._connection.execute(
            """
            UPDATE runs
            SET status = 'blocked', error_json = ?, version = ?, updated_at = ?
            WHERE id = ?
            """,
            (_json(error), version, now, run_id),
        )
        self._event(
            self._connection,
            run_id,
            "run.blocked",
            {
                "status": "blocked",
                "reason": "continuation migration required",
                "version": version,
            },
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            yield self._connection
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        scope_id: str | None = None,
        invocation_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        current = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO run_events (
                id, run_id, scope_id, invocation_id, attempt_id, seq,
                type, payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id("event"),
                run_id,
                scope_id,
                invocation_id,
                attempt_id,
                int(current[0]) + 1,
                event_type,
                _json(payload),
                _now(),
            ),
        )

    @staticmethod
    def _require_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = cast(
            sqlite3.Row | None,
            connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone(),
        )
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return row

    @staticmethod
    def _require_scope(
        connection: sqlite3.Connection, run_id: str, scope_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM scopes WHERE id = ? AND run_id = ?", (scope_id, run_id)
        ).fetchone()
        row = cast(sqlite3.Row | None, row)
        if row is None:
            raise KeyError(f"scope not found: {scope_id}")
        return row

    @staticmethod
    def _require_scope_by_id(connection: sqlite3.Connection, scope_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM scopes WHERE id = ?", (scope_id,)).fetchone()
        row = cast(sqlite3.Row | None, row)
        if row is None:
            raise KeyError(f"scope not found: {scope_id}")
        return row

    @staticmethod
    def _require_invocation(connection: sqlite3.Connection, invocation_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM invocations WHERE id = ?", (invocation_id,)
        ).fetchone()
        row = cast(sqlite3.Row | None, row)
        if row is None:
            raise KeyError(f"invocation not found: {invocation_id}")
        return row

    @staticmethod
    def _require_attempt(connection: sqlite3.Connection, attempt_id: str) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT attempts.*, invocations.run_id, invocations.scope_id
            FROM attempts JOIN invocations ON invocations.id = attempts.invocation_id
            WHERE attempts.id = ?
            """,
            (attempt_id,),
        ).fetchone()
        row = cast(sqlite3.Row | None, row)
        if row is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        return row

    @staticmethod
    def _require_human_request(
        connection: sqlite3.Connection, request_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM human_requests WHERE id = ?", (request_id,)
        ).fetchone()
        row = cast(sqlite3.Row | None, row)
        if row is None:
            raise KeyError(f"human request not found: {request_id}")
        return row


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_or_none(value: Any) -> str | None:
    return None if value is None else _json(value)


def error_output(error: dict[str, Any]) -> dict[str, Any]:
    """Return the stable output exposed to a deterministic error route."""
    return {
        "error": {
            "code": str(error.get("code", "RUNTIME_ERROR")),
            "message": str(error.get("message", "Runtime execution failed.")),
            "retryable": bool(error.get("retryable", False)),
            "details": (
                error.get("details")
                if isinstance(error.get("details"), dict)
                else {}
            ),
            "evidenceRefs": (
                error.get("evidenceRefs")
                if isinstance(error.get("evidenceRefs"), list)
                else []
            ),
            "nextActions": (
                error.get("nextActions")
                if isinstance(error.get("nextActions"), list)
                else []
            ),
        }
    }


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)

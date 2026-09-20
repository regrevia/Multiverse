from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast


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
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'run', ?, 1, NULL, ?, ?, ?, ?)
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
    ) -> dict[str, Any]:
        if not reason.strip():
            raise LedgerConflict("control reason must not be empty")
        with self._transaction() as connection:
            run = self._require_run(connection, run_id)
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
                WHERE id = ?
                """,
                (status, control_mode, version, _now(), run_id),
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
        return self.get_run(run_id)  # type: ignore[return-value]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row(row)

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        current_node_id: str | None = None,
        control_mode: str | None = None,
        output: Any = None,
        error: Any = None,
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
            connection.execute(
                """
                UPDATE runs
                SET status = ?, control_mode = ?, current_node_id = ?,
                    output_json = ?, error_json = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    next_control_mode,
                    current_node_id,
                    _json_or_none(output),
                    _json_or_none(error),
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
                            "currentNodeId": run["current_node_id"],
                            "version": run_version,
                            "reason": "unresolved attempt result",
                        },
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
        if conclusion == "confirmed_failed":
            error = {"code": "RECONCILED_FAILURE", "message": reason}
        elif conclusion == "confirmed_cancelled":
            error = {"code": "RECONCILED_CANCELLED", "message": reason}
        elif conclusion == "confirmed_not_started":
            error = {"code": "RECONCILED_NOT_STARTED", "message": reason}
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
                    _json_or_none(output),
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
        return self.get_attempt(attempt_id)  # type: ignore[return-value]

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
                version INTEGER NOT NULL,
                current_node_id TEXT,
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
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO commands_migrated (
                    id, idempotency_key, fingerprint, operation, namespace,
                    subject, resource_id, status, resource_version, error_json,
                    created_at, updated_at
                )
                SELECT id, idempotency_key, fingerprint, operation, namespace,
                       COALESCE(subject, 'local-user'), resource_id, status,
                       resource_version, error_json, created_at, updated_at
                FROM commands;
                DROP TABLE commands;
                ALTER TABLE commands_migrated RENAME TO commands;
                """
            )
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS commands_scope_key
            ON commands(namespace, subject, operation, idempotency_key)
            """
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
        ):
            if column not in run_columns:
                self._connection.execute(f"ALTER TABLE runs ADD COLUMN {column} {definition}")
        attempt_columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(attempts)").fetchall()
        }
        for column, definition in (
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
        self._connection.commit()

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


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)

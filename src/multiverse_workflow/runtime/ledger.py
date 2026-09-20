from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


class LedgerConflict(RuntimeError):
    """A persisted command cannot be applied to the current resource version."""


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
        workflow_id: str,
        package_digest: str,
        binding_digest: str | None,
        plan: dict[str, Any],
        input_value: Any,
        deadline_at: str,
    ) -> dict[str, Any]:
        run_id = _new_id("run")
        now = _now()
        input_json = _json(input_value)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, namespace, workflow_id, package_digest, binding_digest,
                    plan_json, input_json, input_digest, status, control_mode,
                    deadline_at, version, current_node_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'run', ?, 1, NULL, ?, ?)
                """,
                (
                    run_id,
                    namespace,
                    workflow_id,
                    package_digest,
                    binding_digest,
                    _json(plan),
                    input_json,
                    _digest(input_json),
                    deadline_at,
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
        parent_scope_id: str | None = None,
        parent_invocation_id: str | None = None,
    ) -> dict[str, Any]:
        scope_id = _new_id("scope")
        with self._transaction() as connection:
            self._require_run(connection, run_id)
            connection.execute(
                """
                INSERT INTO scopes (
                    id, run_id, parent_scope_id, parent_invocation_id,
                    workflow_id, path_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    scope_id,
                    run_id,
                    parent_scope_id,
                    parent_invocation_id,
                    workflow_id,
                    _json(path),
                    _now(),
                ),
            )
            self._event(
                connection,
                run_id,
                "scope.created",
                {"scopeId": scope_id, "workflowId": workflow_id},
                scope_id=scope_id,
            )
        return self.get_scope(scope_id)  # type: ignore[return-value]

    def get_scope(self, scope_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM scopes WHERE id = ?", (scope_id,)).fetchone()
        return _row(row)

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
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'created', ?, ?, ?, ?, ?, ?)
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
            connection.execute(
                """
                UPDATE attempts
                SET status = ?, output_json = ?, error_json = ?,
                    external_ref = ?, updated_at = ?
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
                {"attemptId": attempt_id, "status": status},
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
                raise LedgerConflict("human request is already decided")
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

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
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
                output_json TEXT,
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
                status TEXT NOT NULL,
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
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(human_decisions)").fetchall()
        }
        if "decision_json" not in columns:
            self._connection.execute(
                "ALTER TABLE human_decisions ADD COLUMN decision_json TEXT NOT NULL DEFAULT '{}'"
            )
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

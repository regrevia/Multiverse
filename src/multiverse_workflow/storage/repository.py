from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from multiverse_workflow.storage.sqlalchemy import PostgresTransactionStore


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


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
        return self.get_invocation(namespace, invocation_id), self.get_attempt(
            namespace, attempt_id
        )

    def get_invocation(self, namespace: str, invocation_id: str) -> dict[str, Any]:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT invocations.* FROM invocations "
                    "JOIN runs ON runs.id = invocations.run_id "
                    "WHERE invocations.id = :invocation_id AND runs.namespace = :namespace"
                ),
                {"invocation_id": invocation_id, "namespace": namespace},
            ).mappings().first()
        if row is None:
            raise KeyError(f"invocation not found: {invocation_id}")
        return dict(row)

    def get_attempt(self, namespace: str, attempt_id: str) -> dict[str, Any]:
        with self._store.transaction() as connection:
            row = connection.execute(
                text(
                    "SELECT attempts.* FROM attempts "
                    "JOIN runs ON runs.id = attempts.run_id "
                    "WHERE attempts.id = :attempt_id AND runs.namespace = :namespace"
                ),
                {"attempt_id": attempt_id, "namespace": namespace},
            ).mappings().first()
        if row is None:
            raise KeyError(f"attempt not found: {attempt_id}")
        return dict(row)

    def list_invocations(self, namespace: str, run_id: str) -> list[str]:
        with self._store.transaction() as connection:
            rows = connection.execute(
                text(
                    "SELECT invocations.id FROM invocations "
                    "JOIN runs ON runs.id = invocations.run_id "
                    "WHERE invocations.run_id = :run_id AND runs.namespace = :namespace "
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
                    "WHERE attempts.run_id = :run_id AND runs.namespace = :namespace "
                    "ORDER BY attempts.created_at, attempts.attempt_no"
                ),
                {"run_id": run_id, "namespace": namespace},
            ).all()
        return [str(row[0]) for row in rows]

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

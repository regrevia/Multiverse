from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from multiverse_workflow.runtime.catalog import load_executor_registry
from multiverse_workflow.runtime.dispatch_lease import DispatchGate
from multiverse_workflow.runtime.registry import ExecutorRegistry
from multiverse_workflow.runtime.worker import LocalWorker
from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.storage.database import (
    DatabaseTarget,
    DatabaseTargetError,
    parse_database_target,
)

Scope = Literal[
    "read",
    "run:start",
    "run:control",
    "human:decide",
    "codex:interact",
    "session:manage",
    "deploy:write",
    "executor:manage",
    "reconcile:write",
]


@dataclass(frozen=True)
class LocalPrincipal:
    subject: str
    namespace: str
    scopes: frozenset[Scope]


@dataclass(frozen=True)
class ServiceSettings:
    database_path: Path
    package_dir: Path
    binding_path: Path
    deployment_id: str = "deployment_local"
    namespace: str = "local"
    bearer_token: str | None = None
    subject: str = "local-user"
    scopes: frozenset[Scope] = frozenset(
        {
            "read",
            "run:start",
            "run:control",
            "human:decide",
            "codex:interact",
            "session:manage",
            "deploy:write",
            "executor:manage",
            "reconcile:write",
        }
    )
    sse_poll_interval: float = 0.25
    sse_idle_timeout: float = 30.0
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    )

    registry_path: Path | None = None
    executor_registry: ExecutorRegistry | None = field(default=None, repr=False)
    dispatch_gate: DispatchGate | None = field(default=None, repr=False)
    ledger_factory: Any | None = field(default=None, repr=False)
    profile: Literal["personal", "team", "offline"] = "personal"
    _database_target: DatabaseTarget = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.registry_path is not None and self.executor_registry is not None:
            raise ValueError("use registry_path or executor_registry, not both")
        if self.profile not in {"personal", "team", "offline"}:
            raise DatabaseTargetError(
                "profile must be personal, team or offline"
            )
        snapshot = (
            self.executor_registry.snapshot()
            if self.executor_registry is not None
            else load_executor_registry(self.registry_path)
        )
        object.__setattr__(self, "executor_registry", snapshot)
        target = parse_database_target(self.database_path)
        object.__setattr__(self, "_database_target", target)
        if self.profile == "team":
            raise DatabaseTargetError(
                "team profile is not startable yet: PostgreSQL Runtime backend is not wired "
                "to RuntimeApplication/Runner"
            )
        if self.profile == "offline":
            raise DatabaseTargetError(
                "offline profile is not startable yet: offline resource closure and "
                "external-network enforcement are not configured"
            )
        if target.backend != "sqlite":
            raise DatabaseTargetError(
                "personal/offline profiles require an explicit SQLite Path target"
            )
        if not self.deployment_id.strip():
            raise ValueError("deployment_id must not be empty")
        if not self.namespace.strip():
            raise ValueError("namespace must not be empty")
        if not self.subject.strip():
            raise ValueError("subject must not be empty")
        if self.bearer_token is None:
            token = secrets.token_urlsafe(32)
            object.__setattr__(self, "bearer_token", token)
            token_path = self.database_path.expanduser().resolve().parent / "runtime.token"
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(token + "\n", encoding="utf-8")
            os.chmod(token_path, 0o600)

    @property
    def database_target(self) -> DatabaseTarget:
        return self._database_target

    def readiness(self) -> dict[str, Any]:
        database_ready = False
        artifact_ready = False
        database_detail = "database is not available"
        artifact_detail = "artifact storage is not available"
        if self.database_target.backend == "sqlite":
            database_path = self.database_path.expanduser().resolve()
            try:
                if database_path.is_file():
                    connection = sqlite3.connect(
                        f"file:{database_path}?mode=ro",
                        uri=True,
                    )
                    try:
                        connection.execute("SELECT 1").fetchone()
                        required_tables = {
                            "runs",
                            "commands",
                            "scopes",
                            "invocations",
                            "attempts",
                            "human_requests",
                            "human_decisions",
                            "human_progress_intents",
                            "waits",
                            "outbox",
                            "run_events",
                            "artifacts",
                            "codex_interactions",
                            "external_artifact_sources",
                        }
                        actual_tables = {
                            str(row[0])
                            for row in connection.execute(
                                "SELECT name FROM sqlite_master "
                                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                            ).fetchall()
                        }
                        required_columns = {
                            "runs": {"id", "namespace", "status", "version"},
                            "commands": {"id", "idempotency_key", "namespace", "status"},
                            "scopes": {"id", "run_id", "status"},
                            "invocations": {"id", "run_id", "scope_id", "status"},
                            "attempts": {"id", "run_id", "scope_id", "invocation_id"},
                            "human_requests": {"id", "run_id", "version", "status"},
                            "human_decisions": {"id", "request_id", "idempotency_key"},
                            "human_progress_intents": {"id", "request_id", "status"},
                            "waits": {"id", "namespace", "wait_key", "run_id", "status"},
                            "outbox": {"id", "action_key", "attempt_id", "status"},
                            "run_events": {"id", "run_id", "seq", "type"},
                            "artifacts": {"id", "namespace", "run_id", "digest", "status"},
                            "codex_interactions": {"id", "attempt_id", "status"},
                            "external_artifact_sources": {
                                "attempt_id",
                                "execution_ref",
                                "source_artifact_id",
                                "version",
                            },
                        }
                        schema_ready = required_tables.issubset(actual_tables)
                        for table, columns in required_columns.items():
                            actual_columns = {
                                str(row[1])
                                for row in connection.execute(
                                    f'PRAGMA table_info("{table}")'
                                ).fetchall()
                            }
                            if not columns.issubset(actual_columns):
                                schema_ready = False
                        integrity = connection.execute(
                            "PRAGMA integrity_check"
                        ).fetchone()
                        database_ready = (
                            schema_ready
                            and integrity is not None
                            and integrity[0] == "ok"
                        )
                    finally:
                        connection.close()
                    if database_ready:
                        database_detail = "sqlite is readable with the Runtime schema"
                    else:
                        database_detail = "sqlite Runtime schema is incomplete"
            except (OSError, sqlite3.Error):
                database_ready = False
            artifact_root = database_path.parent / "artifacts"
            try:
                artifact_root.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    dir=artifact_root,
                    prefix=".readiness-",
                    delete=True,
                ) as probe:
                    probe.write(b"multiverse-readiness")
                    probe.flush()
                    probe.seek(0)
                    artifact_ready = probe.read() == b"multiverse-readiness"
                if artifact_ready:
                    artifact_detail = "local artifact storage passed write/read probe"
            except OSError:
                artifact_ready = False
        return {
            "status": "ready" if database_ready and artifact_ready else "not_ready",
            "profile": self.profile,
            "databaseBackend": self.database_target.backend,
            "runtimeBackend": "sqlite-ledger",
            "scheduler": "local-single-active",
            "checks": {
                "database": {
                    "status": "ready" if database_ready else "not_ready",
                    "detail": database_detail,
                },
                "artifactStorage": {
                    "status": "ready" if artifact_ready else "not_ready",
                    "detail": artifact_detail,
                },
                "migration": {
                    "status": "ready" if database_ready else "not_ready",
                    "detail": "SQLite Ledger schema is checked during startup",
                },
            },
            "capabilities": {
                "workflowLedger": True,
                "persistentWorker": True,
                "postgresRuntime": False,
                "localArtifactBytes": True,
                "serviceArtifactBytes": False,
            },
            "limitations": [
                "team PostgreSQL Runtime backend is not wired",
                "single-process SQLite deployment",
            ],
        }

    def create_application(self) -> RuntimeApplication:
        return RuntimeApplication(
            package_dir=self.package_dir,
            binding_path=self.binding_path,
            database_path=self.database_path,
            deployment_id=self.deployment_id,
            namespace=self.namespace,
            subject=self.subject,
            executor_registry=self.executor_registry,
            ledger_factory=self.ledger_factory,
        )

    def create_worker(
        self,
        *,
        worker_id: str,
        poll_interval: float = 1.0,
        limit: int = 100,
        claim_timeout_seconds: float = 60.0,
    ) -> LocalWorker:
        """Use the same catalog snapshot as applications created by these settings."""
        return LocalWorker.from_paths(
            package_dir=self.package_dir,
            binding_path=self.binding_path,
            database_path=self.database_path,
            namespace=self.namespace,
            executor_registry=self.executor_registry,
            worker_id=worker_id,
            poll_interval=poll_interval,
            limit=limit,
            claim_timeout_seconds=claim_timeout_seconds,
            dispatch_gate=self.dispatch_gate,
            ledger_factory=self.ledger_factory,
        )

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from multiverse_workflow.runtime.catalog import load_executor_registry
from multiverse_workflow.runtime.registry import ExecutorRegistry
from multiverse_workflow.runtime.worker import LocalWorker
from multiverse_workflow.service.application import RuntimeApplication

Scope = Literal[
    "read",
    "run:start",
    "run:control",
    "human:decide",
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

    def __post_init__(self) -> None:
        if self.registry_path is not None and self.executor_registry is not None:
            raise ValueError("use registry_path or executor_registry, not both")
        snapshot = (
            self.executor_registry.snapshot()
            if self.executor_registry is not None
            else load_executor_registry(self.registry_path)
        )
        object.__setattr__(self, "executor_registry", snapshot)
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

    def create_application(self) -> RuntimeApplication:
        return RuntimeApplication(
            package_dir=self.package_dir,
            binding_path=self.binding_path,
            database_path=self.database_path,
            deployment_id=self.deployment_id,
            namespace=self.namespace,
            subject=self.subject,
            executor_registry=self.executor_registry,
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
        )

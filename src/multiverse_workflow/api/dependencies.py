from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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

    def __post_init__(self) -> None:
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
        )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from multiverse_workflow.service.application import RuntimeApplication


@dataclass(frozen=True)
class ServiceSettings:
    database_path: Path
    package_dir: Path
    binding_path: Path
    namespace: str = "local"
    bearer_token: str | None = None
    sse_poll_interval: float = 0.25
    sse_idle_timeout: float = 30.0

    def create_application(self) -> RuntimeApplication:
        return RuntimeApplication(
            package_dir=self.package_dir,
            binding_path=self.binding_path,
            database_path=self.database_path,
            namespace=self.namespace,
        )

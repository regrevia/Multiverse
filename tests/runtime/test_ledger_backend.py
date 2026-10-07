from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.runtime.runner import RunError, Runner

ROOT = Path(__file__).parents[2]


def test_runner_rejects_backend_missing_runtime_methods(tmp_path: Path) -> None:
    class IncompleteBackend:
        def close(self) -> None:
            return None

    with pytest.raises(RunError, match="ledger backend is incompatible"):
        Runner(
            ROOT / "presets/content-delivery",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=tmp_path / "runtime.db",
            ledger_factory=lambda _path: IncompleteBackend(),
        )


def test_runner_rejects_backend_missing_node_lookup(tmp_path: Path) -> None:
    class IncompleteBackend:
        def close(self) -> None:
            return None

    with pytest.raises(RunError, match="get_invocation_for_node"):
        Runner(
            ROOT / "presets/content-delivery",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=tmp_path / "runtime.db",
            ledger_factory=lambda _path: IncompleteBackend(),
        )


def test_runtime_application_closes_ledger_when_command_store_bind_fails(
    tmp_path: Path,
) -> None:
    from multiverse_workflow.service.application import RuntimeApplication

    created: list[Ledger] = []

    def factory(path: Path) -> Ledger:
        ledger = Ledger(path)
        created.append(ledger)
        return ledger

    class UnboundStore:
        def assert_bound_to(self, _ledger: Ledger) -> None:
            raise ValueError("unbound command store")

    with pytest.raises(ValueError, match="unbound command store"):
        RuntimeApplication(
            package_dir=ROOT / "presets/content-delivery",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=tmp_path / "runtime.db",
            ledger_factory=factory,
            command_store_factory=lambda _ledger: UnboundStore(),  # type: ignore[arg-type]
        )
    assert created

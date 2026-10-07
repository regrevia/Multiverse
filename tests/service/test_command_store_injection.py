from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.command_store import LedgerCommandStore
from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.service.application import RuntimeApplication


def test_runtime_application_uses_injected_command_store(tmp_path: Path) -> None:
    application = RuntimeApplication(
        package_dir=Path("presets/content-delivery"),
        binding_path=Path("examples/bindings/content-local.yaml"),
        database_path=tmp_path / "runtime.db",
        command_store_factory=LedgerCommandStore,
    )
    try:
        assert isinstance(application.command_store, LedgerCommandStore)
    finally:
        application.close()


def test_runtime_application_rejects_unbound_command_store_factory(
    tmp_path: Path,
) -> None:
    class UnboundStore:
        def assert_bound_to(self, _ledger: Ledger) -> None:
            raise ValueError("unbound command store")

    with pytest.raises(ValueError, match="unbound command store"):
        RuntimeApplication(
            package_dir=Path("presets/content-delivery"),
            binding_path=Path("examples/bindings/content-local.yaml"),
            database_path=tmp_path / "runtime.db",
            command_store_factory=lambda _ledger: UnboundStore(),  # type: ignore[arg-type]
        )

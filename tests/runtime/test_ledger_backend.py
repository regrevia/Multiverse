from __future__ import annotations

import ast
from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.runtime.ledger_backend import (
    LEDGER_BACKEND_METHODS,
    LedgerBackendError,
    validate_ledger_backend,
)
from multiverse_workflow.runtime.runner import RunError, Runner

ROOT = Path(__file__).parents[2]


def test_sqlite_ledger_satisfies_the_shared_runner_backend_contract(
    tmp_path: Path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    try:
        validate_ledger_backend(ledger)
        assert "create_queued_run" in LEDGER_BACKEND_METHODS
        assert len(LEDGER_BACKEND_METHODS) >= 60
    finally:
        ledger.close()


def test_partial_backend_is_rejected_by_the_shared_contract() -> None:
    class IncompleteBackend:
        def close(self) -> None:
            return None

    with pytest.raises(LedgerBackendError, match="ledger backend is incompatible"):
        validate_ledger_backend(IncompleteBackend())


def test_contract_matches_every_direct_runner_ledger_call() -> None:
    runner_source = (ROOT / "src/multiverse_workflow/runtime/runner.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(runner_source)
    runner_calls = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "ledger"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    }
    assert runner_calls <= set(LEDGER_BACKEND_METHODS)
    assert len(LEDGER_BACKEND_METHODS) == 68


def test_backend_methods_must_accept_ledger_public_parameters() -> None:
    class NoArgumentBackend:
        pass

    for name in LEDGER_BACKEND_METHODS:
        setattr(NoArgumentBackend, name, lambda self: None)

    with pytest.raises(LedgerBackendError, match="cannot accept"):
        validate_ledger_backend(NoArgumentBackend())


def test_backend_methods_must_match_positional_and_required_shapes() -> None:
    class WrongShapeBackend:
        pass

    for name in LEDGER_BACKEND_METHODS:
        if name == "close":
            setattr(WrongShapeBackend, name, lambda self, required: None)
        else:
            setattr(WrongShapeBackend, name, lambda self, **kwargs: None)

    with pytest.raises(LedgerBackendError, match="cannot accept"):
        validate_ledger_backend(WrongShapeBackend())


def test_backend_methods_must_not_hide_the_contract_behind_kwargs() -> None:
    class KwargsOnlyBackend:
        pass

    for name in LEDGER_BACKEND_METHODS:
        setattr(KwargsOnlyBackend, name, lambda self, **kwargs: None)

    with pytest.raises(LedgerBackendError, match="cannot hide"):
        validate_ledger_backend(KwargsOnlyBackend())


def test_backend_attribute_errors_are_reported_as_contract_errors() -> None:
    class ExplodingBackend:
        def __getattribute__(self, name: str):
            if name == "close":
                raise RuntimeError("attribute probe failed")
            return super().__getattribute__(name)

    with pytest.raises(LedgerBackendError, match="could not inspect"):
        validate_ledger_backend(ExplodingBackend())


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


def test_runner_close_is_idempotent(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    runner.close()
    runner.close()


def test_application_close_is_idempotent(tmp_path: Path) -> None:
    from multiverse_workflow.service.application import RuntimeApplication

    application = RuntimeApplication(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    application.close()
    application.close()

from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.dispatch_lease import (
    DispatchLeaseLost,
    NoopDispatchGate,
)
from multiverse_workflow.runtime.registry import local_executor_registry
from multiverse_workflow.runtime.runner import RunError
from multiverse_workflow.runtime.worker import LocalWorker, WorkerLockError

ROOT = Path(__file__).parents[2]


def test_noop_dispatch_gate_allows_local_dispatch() -> None:
    NoopDispatchGate().assert_can_dispatch()


def test_lost_dispatch_gate_fails_closed() -> None:
    class LostGate:
        def assert_can_dispatch(self) -> None:
            raise DispatchLeaseLost("lease lost")

    with pytest.raises(DispatchLeaseLost, match="lease lost"):
        LostGate().assert_can_dispatch()


def test_worker_checks_dispatch_gate_before_sweeping() -> None:
    class LostGate:
        def assert_can_dispatch(self) -> None:
            raise DispatchLeaseLost("lease lost")

    class WorkerHarness:
        dispatch_gate = LostGate()

        def _ensure_open(self) -> None:
            return None

    with pytest.raises(DispatchLeaseLost, match="lease lost"):
        LocalWorker.run_once(WorkerHarness())  # type: ignore[arg-type]


def test_dispatch_gate_close_is_idempotent(tmp_path: Path) -> None:
    class Gate:
        released = 0
        closed = 0

        def assert_can_dispatch(self) -> None:
            return None

        def release(self) -> None:
            self.released += 1

        def close(self) -> None:
            self.closed += 1

    lock_file = (tmp_path / "worker.lock").open("w+", encoding="utf-8")
    worker = object.__new__(LocalWorker)
    worker.runner = type("Runner", (), {"close": lambda self: None})()
    worker.dispatch_gate = Gate()
    worker._dispatch_gate_acquired = True
    worker._lock_file = lock_file
    worker._closed = False
    worker.close()
    worker.close()
    assert worker.dispatch_gate.closed == 1
    assert worker.dispatch_gate.released == 1


def test_worker_releases_local_lock_when_gate_close_fails(tmp_path: Path) -> None:
    class FailingGate:
        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            raise RuntimeError("gate close failed")

        def release(self) -> None:
            return None

    lock_path = tmp_path / "worker.lock"
    lock_file = lock_path.open("a+", encoding="utf-8")
    worker = object.__new__(LocalWorker)
    worker.runner = type("Runner", (), {"close": lambda self: None})()
    worker.dispatch_gate = FailingGate()
    worker._dispatch_gate_acquired = True
    worker._lock_file = lock_file
    worker._closed = False
    with pytest.raises(RuntimeError, match="gate close failed"):
        worker.close()
    assert lock_file.closed is True


def test_worker_factory_preserves_falsey_dispatch_gate(tmp_path: Path) -> None:
    class FalseyGate:
        def __bool__(self) -> bool:
            return False

        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            return None

    gate = FalseyGate()
    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="falsey-gate-worker",
        dispatch_gate=gate,  # type: ignore[arg-type]
        executor_registry=local_executor_registry(),
    )
    try:
        assert worker.dispatch_gate is gate
    finally:
        worker.close()


def test_worker_factory_closes_gate_and_releases_lock_on_runner_failure(
    tmp_path: Path,
) -> None:
    class TrackingGate:
        closed = False

        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    gate = TrackingGate()
    database = tmp_path / "runtime.db"
    with pytest.raises(RunError):
        LocalWorker.from_paths(
            package_dir=tmp_path / "missing-package",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=database,
            worker_id="failed-runner-worker",
            dispatch_gate=gate,  # type: ignore[arg-type]
            executor_registry=local_executor_registry(),
        )
    assert gate.closed is True

    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=database,
        worker_id="recovered-runner-worker",
        executor_registry=local_executor_registry(),
    )
    worker.close()


def test_worker_factory_closes_runner_gate_and_lock_on_worker_init_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TrackingGate:
        closed = False

        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    gate = TrackingGate()
    closed_runners: list[object] = []

    class FakeRunner:
        def __init__(self, *_: object, **__: object) -> None:
            self.namespace = "local"

        def close(self) -> None:
            closed_runners.append(self)

    def fail_worker_init(*_: object, **__: object) -> LocalWorker:
        raise RuntimeError("worker recovery init failed")

    monkeypatch.setattr("multiverse_workflow.runtime.worker.Runner", FakeRunner)
    monkeypatch.setattr(LocalWorker, "__init__", fail_worker_init)
    database = tmp_path / "runtime.db"
    with pytest.raises(RuntimeError, match="worker recovery init failed"):
        LocalWorker.from_paths(
            package_dir=ROOT / "presets/content-delivery",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=database,
            worker_id="failed-init-worker",
            dispatch_gate=gate,  # type: ignore[arg-type]
        )

    assert gate.closed is True
    assert len(closed_runners) == 1
    monkeypatch.undo()
    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=database,
        worker_id="recovered-init-worker",
        executor_registry=local_executor_registry(),
    )
    worker.close()


def test_worker_factory_closes_gate_when_local_lock_is_held(tmp_path: Path) -> None:
    class TrackingGate:
        closed = False

        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    database = tmp_path / "runtime.db"
    first = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=database,
        worker_id="lock-owner",
        executor_registry=local_executor_registry(),
    )
    gate = TrackingGate()
    try:
        with pytest.raises(WorkerLockError, match="already held"):
            LocalWorker.from_paths(
                package_dir=ROOT / "presets/content-delivery",
                binding_path=ROOT / "examples/bindings/content-local.yaml",
                database_path=database,
                worker_id="lock-contender",
                dispatch_gate=gate,  # type: ignore[arg-type]
                executor_registry=local_executor_registry(),
            )
        assert gate.closed is True
    finally:
        first.close()


def test_worker_factory_acquires_and_releases_explicit_gate(tmp_path: Path) -> None:
    class Gate:
        acquired = 0
        released = 0
        closed = 0

        def acquire(self) -> bool:
            self.acquired += 1
            return True

        def assert_can_dispatch(self) -> None:
            return None

        def release(self) -> None:
            self.released += 1

        def close(self) -> None:
            self.closed += 1

    gate = Gate()
    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="acquire-gate-worker",
        dispatch_gate=gate,  # type: ignore[arg-type]
        executor_registry=local_executor_registry(),
    )
    assert gate.acquired == 1
    worker.close()
    assert gate.released == 1
    assert gate.closed == 1


def test_worker_factory_rejects_gate_that_cannot_acquire(tmp_path: Path) -> None:
    class Gate:
        closed = 0

        def acquire(self) -> bool:
            return False

        def close(self) -> None:
            self.closed += 1

    gate = Gate()
    with pytest.raises(WorkerLockError, match="dispatch lease"):
        LocalWorker.from_paths(
            package_dir=ROOT / "presets/content-delivery",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=tmp_path / "runtime.db",
            worker_id="rejected-gate-worker",
            dispatch_gate=gate,  # type: ignore[arg-type]
            executor_registry=local_executor_registry(),
        )
    assert gate.closed == 1

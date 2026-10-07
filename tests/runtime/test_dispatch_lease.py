from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.dispatch_lease import (
    DispatchLeaseLost,
    NoopDispatchGate,
)
from multiverse_workflow.runtime.worker import LocalWorker


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
        closed = 0

        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            self.closed += 1

    lock_file = (tmp_path / "worker.lock").open("w+", encoding="utf-8")
    worker = object.__new__(LocalWorker)
    worker.runner = type("Runner", (), {"close": lambda self: None})()
    worker.dispatch_gate = Gate()
    worker._lock_file = lock_file
    worker._closed = False
    worker.close()
    worker.close()
    assert worker.dispatch_gate.closed == 1


def test_worker_releases_local_lock_when_gate_close_fails(tmp_path: Path) -> None:
    class FailingGate:
        def assert_can_dispatch(self) -> None:
            return None

        def close(self) -> None:
            raise RuntimeError("gate close failed")

    lock_path = tmp_path / "worker.lock"
    lock_file = lock_path.open("a+", encoding="utf-8")
    worker = object.__new__(LocalWorker)
    worker.runner = type("Runner", (), {"close": lambda self: None})()
    worker.dispatch_gate = FailingGate()
    worker._lock_file = lock_file
    worker._closed = False
    with pytest.raises(RuntimeError, match="gate close failed"):
        worker.close()
    assert lock_file.closed is True

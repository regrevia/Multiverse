from __future__ import annotations

import fcntl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, TextIO

from multiverse_workflow.runtime.dispatch_lease import (
    DispatchGate,
    NoopDispatchGate,
)
from multiverse_workflow.runtime.registry import ExecutorRegistry
from multiverse_workflow.runtime.runner import Runner


class WorkerLockError(RuntimeError):
    """Another local Worker already owns the SQLite runtime lock."""


def _cleanup_dispatch_gate(gate: DispatchGate, *, acquired: bool) -> None:
    cleanup_error: BaseException | None = None
    if acquired:
        release_gate = getattr(gate, "release", None)
        if callable(release_gate):
            try:
                release_gate()
            except BaseException as exc:
                cleanup_error = exc
    close_gate = getattr(gate, "close", None)
    if callable(close_gate):
        try:
            close_gate()
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
            else:
                cleanup_error.add_note(f"dispatch gate close failed: {exc}")
    if cleanup_error is not None:
        raise cleanup_error


class LocalWorker:
    """A single-active local scheduler for durable SQLite waits."""

    def __init__(
        self,
        runner: Runner,
        *,
        lock_file: TextIO,
        worker_id: str,
        poll_interval: float,
        limit: int,
        claim_timeout_seconds: float,
        dispatch_gate: DispatchGate,
        dispatch_gate_acquired: bool = False,
    ) -> None:
        self.runner = runner
        self.worker_id = worker_id
        self.poll_interval = poll_interval
        self.limit = limit
        self.claim_timeout_seconds = claim_timeout_seconds
        self.dispatch_gate = dispatch_gate
        self._dispatch_gate_acquired = dispatch_gate_acquired
        self._lock_file = lock_file
        self._closed = False
        self._recover_codex_interactions()

    @classmethod
    def from_paths(
        cls,
        *,
        package_dir: Path,
        binding_path: Path,
        database_path: Path,
        worker_id: str,
        namespace: str = "local",
        poll_interval: float = 1.0,
        limit: int = 100,
        claim_timeout_seconds: float = 60.0,
        executor_registry: ExecutorRegistry | None = None,
        dispatch_gate: DispatchGate | None = None,
        ledger_factory: Any | None = None,
    ) -> LocalWorker:
        if not worker_id.strip():
            raise ValueError("worker id is required")
        if poll_interval < 0:
            raise ValueError("poll interval must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        if claim_timeout_seconds < 0:
            raise ValueError("claim timeout must be non-negative")

        database_path = database_path.expanduser().resolve()
        gate = dispatch_gate if dispatch_gate is not None else NoopDispatchGate()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = Path(f"{database_path}.worker.lock")
        lock_file = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_error = WorkerLockError(
                f"worker lock is already held for database: {database_path}"
            )
            try:
                close_gate = getattr(gate, "close", None)
                if callable(close_gate):
                    close_gate()
            except BaseException as cleanup_error:
                lock_error.add_note(f"dispatch gate cleanup failed: {cleanup_error}")
            finally:
                lock_file.close()
            raise lock_error from exc

        gate_acquired = False
        runner: Runner | None = None
        try:
            acquire_gate = getattr(gate, "acquire", None)
            if callable(acquire_gate):
                if not acquire_gate():
                    raise WorkerLockError("dispatch lease is already held")
                gate_acquired = True
            runner = Runner(
                package_dir,
                binding_path=binding_path,
                database_path=database_path,
                namespace=namespace,
                executor_registry=executor_registry,
                ledger_factory=ledger_factory,
            )
            return cls(
                runner,
                lock_file=lock_file,
                worker_id=worker_id,
                poll_interval=poll_interval,
                limit=limit,
                claim_timeout_seconds=claim_timeout_seconds,
                dispatch_gate=gate,
                dispatch_gate_acquired=gate_acquired,
            )
        except BaseException as construction_error:
            if runner is not None:
                try:
                    runner.close()
                except BaseException as cleanup_error:
                    construction_error.add_note(
                        f"runner cleanup failed: {cleanup_error}"
                    )
            try:
                _cleanup_dispatch_gate(gate, acquired=gate_acquired)
            except BaseException as cleanup_error:
                construction_error.add_note(
                    f"dispatch gate cleanup failed: {cleanup_error}"
                )
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            raise

    def run_once(self) -> list[dict[str, Any]]:
        self._ensure_open()
        self.dispatch_gate.assert_can_dispatch()
        now = datetime.now(UTC)
        now_text = _timestamp(now)
        cutoff = _timestamp(now - timedelta(seconds=self.claim_timeout_seconds))
        self.runner.wait_store.requeue_stale_waits(
            now=now_text,
            older_than=cutoff,
            namespace=self.runner.namespace,
        )
        return self.runner.sweep(
            worker_id=self.worker_id,
            now=now_text,
            limit=self.limit,
        )

    def run_forever(
        self,
        *,
        stop_event: Event | None = None,
        max_cycles: int | None = None,
    ) -> int:
        self._ensure_open()
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max cycles must be positive")
        stop_event = stop_event or Event()
        cycles = 0
        while not stop_event.is_set() and (
            max_cycles is None or cycles < max_cycles
        ):
            self.run_once()
            cycles += 1
            if (
                not stop_event.is_set()
                and (max_cycles is None or cycles < max_cycles)
                and self.poll_interval > 0
            ):
                stop_event.wait(self.poll_interval)
        return cycles

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.runner.close()
        finally:
            try:
                _cleanup_dispatch_gate(
                    self.dispatch_gate,
                    acquired=getattr(self, "_dispatch_gate_acquired", False),
                )
            finally:
                try:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                finally:
                    self._lock_file.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("worker is closed")

    def _recover_codex_interactions(self) -> None:
        for interaction in self.runner.ledger.list_codex_interactions(
            namespace=self.runner.namespace
        ):
            if not (
                interaction["status"] == "pending"
                or (
                    interaction["status"] == "replied"
                    and interaction.get("delivery_status") in {"pending", "sent"}
                )
            ):
                continue
            self.runner.ledger.invalidate_codex_interactions_for_attempt(
                interaction["attempt_id"],
                reason="worker restart invalidated the native Codex interaction",
            )
            attempt = self.runner.ledger.get_attempt(interaction["attempt_id"])
            if attempt is not None and attempt["status"] not in {
                "succeeded",
                "failed",
                "cancelled",
                "unknown",
            }:
                self.runner.ledger.finish_attempt(
                    attempt["id"],
                    status="unknown",
                    error={
                        "code": "CODEX_CONNECTION_LOST",
                        "message": "Worker restart invalidated the native Codex interaction.",
                    },
                )
                attempt = self.runner.ledger.get_attempt(attempt["id"])
            if attempt is not None and attempt["status"] == "unknown":
                self.runner.ledger.ensure_attempt_reconciliation_wait(
                    attempt["id"], allow_unknown=True
                )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )

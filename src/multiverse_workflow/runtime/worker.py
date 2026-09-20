from __future__ import annotations

import fcntl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, TextIO

from multiverse_workflow.runtime.runner import Runner


class WorkerLockError(RuntimeError):
    """Another local Worker already owns the SQLite runtime lock."""


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
    ) -> None:
        self.runner = runner
        self.worker_id = worker_id
        self.poll_interval = poll_interval
        self.limit = limit
        self.claim_timeout_seconds = claim_timeout_seconds
        self._lock_file = lock_file
        self._closed = False

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
        database_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = Path(f"{database_path}.worker.lock")
        lock_file = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise WorkerLockError(
                f"worker lock is already held for database: {database_path}"
            ) from exc

        try:
            runner = Runner(
                package_dir,
                binding_path=binding_path,
                database_path=database_path,
                namespace=namespace,
            )
        except Exception:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            raise
        return cls(
            runner,
            lock_file=lock_file,
            worker_id=worker_id,
            poll_interval=poll_interval,
            limit=limit,
            claim_timeout_seconds=claim_timeout_seconds,
        )

    def run_once(self) -> list[dict[str, Any]]:
        self._ensure_open()
        now = datetime.now(UTC)
        now_text = _timestamp(now)
        cutoff = _timestamp(now - timedelta(seconds=self.claim_timeout_seconds))
        self.runner.ledger.requeue_stale_waits(
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
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("worker is closed")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )

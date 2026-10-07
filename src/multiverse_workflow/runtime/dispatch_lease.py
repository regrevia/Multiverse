from __future__ import annotations

from typing import Protocol

from multiverse_workflow.storage.postgres import (
    PostgresLeaseLost,
    PostgresSingleActiveLease,
)


class DispatchLeaseLost(RuntimeError):
    """The scheduler must stop creating new work."""


class DispatchGate(Protocol):
    def assert_can_dispatch(self) -> None: ...


class NoopDispatchGate:
    """Local SQLite mode has its own process lock and needs no DB lease."""

    def assert_can_dispatch(self) -> None:
        return None

    def close(self) -> None:
        return None


class PostgresDispatchGate:
    """Translate the PostgreSQL single-active lease into a Worker gate."""

    def __init__(self, lease: PostgresSingleActiveLease) -> None:
        self._lease = lease

    def assert_can_dispatch(self) -> None:
        try:
            self._lease.assert_held()
        except PostgresLeaseLost as exc:
            raise DispatchLeaseLost(str(exc)) from exc

    def acquire(self) -> bool:
        return self._lease.acquire()

    def release(self) -> None:
        self._lease.release()

    def close(self) -> None:
        self._lease.close()

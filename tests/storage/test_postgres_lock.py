from __future__ import annotations

import os
import uuid

import pytest

from multiverse_workflow.runtime.dispatch_lease import (
    DispatchLeaseLost,
    PostgresDispatchGate,
)
from multiverse_workflow.storage import postgres
from multiverse_workflow.storage.postgres import (
    PostgresLeaseLost,
    PostgresSingleActiveLease,
    PostgresStorageError,
)

pytestmark = pytest.mark.integration


def _dsn() -> str:
    return os.environ.get("MULTIVERSE_POSTGRES_DSN", "")


def _lock_key() -> int:
    return int.from_bytes(uuid.uuid4().bytes[:8], "big", signed=True)


def test_postgres_advisory_lock_is_single_active() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the real PostgreSQL lock test")

    lock_key = _lock_key()
    first = PostgresSingleActiveLease(dsn, lock_key=lock_key)
    second = PostgresSingleActiveLease(dsn, lock_key=lock_key)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        first.assert_held()
        first.release()
        assert second.acquire() is True
    finally:
        first.close()
        second.close()


def test_postgres_lease_loss_fails_closed() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the real PostgreSQL lock test")

    lease = PostgresSingleActiveLease(dsn, lock_key=_lock_key())
    assert lease.acquire() is True
    lease.close_connection_for_test()
    with pytest.raises(PostgresLeaseLost):
        lease.assert_held()
    lease.close()


def test_postgres_context_manager_releases_after_exception() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the real PostgreSQL lock test")

    lock_key = _lock_key()
    lease = PostgresSingleActiveLease(dsn, lock_key=lock_key)
    with pytest.raises(RuntimeError, match="triggered"):
        with lease:
            raise RuntimeError("triggered")

    next_lease = PostgresSingleActiveLease(dsn, lock_key=lock_key)
    try:
        assert next_lease.acquire() is True
    finally:
        next_lease.close()
        lease.close()


class _FakeCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, *_: object) -> None:
        return None

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row


class _FakeConnection:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.row)

    def close(self) -> None:
        self.closed = True


def test_release_requires_database_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeConnection((False,))
    monkeypatch.setattr(postgres.psycopg, "connect", lambda *args, **kwargs: connection)
    lease = PostgresSingleActiveLease("postgresql:///postgres", lock_key=812_152)
    lease._connection = connection
    lease._held = True

    with pytest.raises(PostgresLeaseLost, match="release"):
        lease.release()
    assert connection.closed is True


def test_dispatch_gate_translates_lease_loss() -> None:
    class LostLease:
        def assert_held(self) -> None:
            raise PostgresLeaseLost("connection lost")

    with pytest.raises(DispatchLeaseLost, match="connection lost"):
        PostgresDispatchGate(LostLease()).assert_can_dispatch()  # type: ignore[arg-type]


def test_release_requires_unlock_result_row(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeConnection(None)
    monkeypatch.setattr(postgres.psycopg, "connect", lambda *args, **kwargs: connection)
    lease = PostgresSingleActiveLease("postgresql:///postgres", lock_key=812_154)
    lease._connection = connection
    lease._held = True

    with pytest.raises(PostgresLeaseLost, match="release"):
        lease.release()
    assert connection.closed is True


def test_release_and_close_are_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _FakeConnection((True,))
    monkeypatch.setattr(postgres.psycopg, "connect", lambda *args, **kwargs: connection)
    lease = PostgresSingleActiveLease("postgresql:///postgres", lock_key=812_155)
    lease._connection = connection
    lease._held = True

    lease.release()
    lease.release()
    lease.close()
    lease.close()
    assert connection.closed is True


def test_acquire_closes_connection_when_lock_query_has_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(None)
    monkeypatch.setattr(postgres.psycopg, "connect", lambda *args, **kwargs: connection)
    lease = PostgresSingleActiveLease("postgresql:///postgres", lock_key=812_153)

    with pytest.raises(PostgresStorageError, match="no row"):
        lease.acquire()
    assert connection.closed is True

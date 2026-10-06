from __future__ import annotations

from typing import Any

import psycopg


class PostgresStorageError(RuntimeError):
    """A PostgreSQL storage operation failed."""


class PostgresLeaseLost(PostgresStorageError):
    """The dedicated single-active-worker connection is no longer usable."""


class PostgresSingleActiveLease:
    """Hold a PostgreSQL advisory lock on a dedicated connection.

    The connection is intentionally retained for the lifetime of the lease.
    Losing it invalidates the lease and callers must stop new dispatch.
    """

    def __init__(self, dsn: str, *, lock_key: int) -> None:
        if not dsn.strip():
            raise ValueError("PostgreSQL DSN must not be empty")
        if not -(2**63) <= lock_key < 2**63:
            raise ValueError("PostgreSQL advisory lock key must fit int64")
        self._dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        self._lock_key = lock_key
        self._connection: psycopg.Connection[Any] | None = None
        self._held = False

    def acquire(self) -> bool:
        if self._connection is not None:
            return self._held
        connection: psycopg.Connection[Any] | None = None
        try:
            connection = psycopg.connect(self._dsn, autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (self._lock_key,))
                row = cursor.fetchone()
                if row is None:
                    raise PostgresStorageError("PostgreSQL lock query returned no row")
                acquired = bool(row[0])
        except (psycopg.Error, PostgresStorageError) as exc:
            if connection is not None:
                connection.close()
            if isinstance(exc, PostgresStorageError):
                raise
            raise PostgresStorageError("could not acquire PostgreSQL advisory lock") from exc
        if not acquired:
            connection.close()
            return False
        self._connection = connection
        self._held = True
        return True

    def assert_held(self) -> None:
        connection = self._connection
        if connection is None or not self._held:
            raise PostgresLeaseLost("PostgreSQL single-active lease is not held")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except psycopg.Error as exc:
            self._held = False
            self.close()
            raise PostgresLeaseLost("PostgreSQL single-active lease connection was lost") from exc

    def release(self) -> None:
        connection = self._connection
        if connection is None:
            self._held = False
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (self._lock_key,))
                row = cursor.fetchone()
                if row is None or row[0] is not True:
                    raise PostgresLeaseLost(
                        "PostgreSQL advisory lock release was not confirmed"
                    )
        except PostgresLeaseLost:
            self._held = False
            self.close()
            raise
        except psycopg.Error as exc:
            self._held = False
            self.close()
            raise PostgresLeaseLost("PostgreSQL advisory lock release was not confirmed") from exc
        self._held = False
        self.close()

    def close_connection_for_test(self) -> None:
        """Simulate a lost dedicated connection in integration tests."""
        if self._connection is not None:
            self._connection.close()

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        self._held = False
        if connection is not None:
            connection.close()

    def __enter__(self) -> PostgresSingleActiveLease:
        if not self.acquire():
            raise PostgresStorageError("PostgreSQL single-active lease is already held")
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

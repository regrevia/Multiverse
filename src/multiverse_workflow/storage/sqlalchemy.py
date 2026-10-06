from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine, Result


class PostgresTransactionStore:
    """Small SQLAlchemy transaction boundary for the PostgreSQL service profile.

    This is deliberately separate from the SQLite Ledger until the shared
    repository contract and migrations are ready.
    """

    def __init__(self, dsn: str) -> None:
        if not dsn.strip():
            raise ValueError("PostgreSQL DSN must not be empty")
        normalized = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        if not normalized.startswith("postgresql+psycopg://"):
            raise ValueError("PostgreSQL DSN must use postgresql+psycopg")
        self._engine: Engine = create_engine(normalized, pool_pre_ping=True)

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self._engine.begin() as connection:
            yield connection

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> Result[Any]:
        with self._engine.begin() as connection:
            return connection.execute(statement, parameters or {})

    def health(self) -> dict[str, str]:
        with self._engine.connect() as connection:
            version: Any = connection.execute(text("SELECT version()")).scalar_one()
        return {"backend": "postgresql", "serverVersion": str(version)}

    def close(self) -> None:
        self._engine.dispose()

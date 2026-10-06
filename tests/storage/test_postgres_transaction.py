from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from multiverse_workflow.storage.sqlalchemy import PostgresTransactionStore

pytestmark = pytest.mark.integration


def _dsn() -> str:
    return os.environ.get("MULTIVERSE_POSTGRES_DSN", "")


def test_postgres_transaction_commits_and_rolls_back() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the real PostgreSQL transaction test")

    table_name = f"mv_test_{uuid.uuid4().hex}"
    store = PostgresTransactionStore(dsn)
    try:
        store.execute(
            text(
                f"CREATE TABLE {table_name} "
                "(id integer primary key, value text not null)"
            )
        )
        with store.transaction() as connection:
            connection.execute(
                text(f"INSERT INTO {table_name} (id, value) VALUES (1, 'committed')")
            )

        with pytest.raises(RuntimeError, match="rollback"):
            with store.transaction() as connection:
                connection.execute(
                    text(f"INSERT INTO {table_name} (id, value) VALUES (2, 'rolled back')")
                )
                raise RuntimeError("rollback")

        rows = store.execute(text(f"SELECT id, value FROM {table_name} ORDER BY id")).all()
        assert [(row.id, row.value) for row in rows] == [(1, "committed")]
        store.execute(text(f"DROP TABLE {table_name}"))
    finally:
        store.close()


def test_postgres_transaction_health_uses_real_database() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the real PostgreSQL transaction test")

    store = PostgresTransactionStore(dsn)
    try:
        assert store.health()["backend"] == "postgresql"
        assert store.health()["serverVersion"].startswith("PostgreSQL ")
    finally:
        store.close()


def test_transaction_store_accepts_standard_postgresql_url() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the real PostgreSQL transaction test")

    standard_dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    store = PostgresTransactionStore(standard_dsn)
    try:
        assert store.health()["backend"] == "postgresql"
    finally:
        store.close()

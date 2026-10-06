from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]


def test_postgres_migrations_create_storage_meta_table() -> None:
    dsn = os.environ.get("MULTIVERSE_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for PostgreSQL migration tests")

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", dsn)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(dsn)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT version_num FROM alembic_version "
                    "WHERE version_num = '0001_storage_meta'"
                )
            ).fetchone()
            assert row is not None
            assert connection.execute(
                text(
                    "SELECT to_regclass('public.multiverse_storage_meta')"
                )
            ).scalar_one() == "multiverse_storage_meta"
        command.downgrade(config, "base")
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT to_regclass('public.multiverse_storage_meta')")
            ).scalar_one() is None
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_alembic_uses_database_url_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg:///missing_database_for_test")
    with pytest.raises(OperationalError):
        command.current(config)


def test_alembic_accepts_percent_encoded_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:p%40ss@127.0.0.1:1/missing_database",
    )
    with pytest.raises(OperationalError):
        command.current(config)

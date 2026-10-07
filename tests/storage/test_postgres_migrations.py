from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, NoSuchModuleError, OperationalError

from multiverse_workflow.runtime.ledger import Ledger

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]


@contextmanager
def _isolated_postgres_schema(dsn: str) -> Iterator[str]:
    schema = f"mv_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(dsn)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        isolated = make_url(dsn).update_query_dict(
            {"options": f"-csearch_path={schema}"},
            append=True,
        )
        isolated_dsn = isolated.render_as_string(hide_password=False)
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = isolated_dsn
        try:
            yield isolated_dsn
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _alembic_config(dsn: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    return config


def test_postgres_migrations_create_storage_and_ledger_tables() -> None:
    dsn = os.environ.get("MULTIVERSE_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for PostgreSQL migration tests")

    with _isolated_postgres_schema(dsn) as test_dsn:
        config = _alembic_config(test_dsn)
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        engine = create_engine(test_dsn)
        expected = {
            "alembic_version",
            "multiverse_storage_meta",
            "runs",
            "commands",
            "scopes",
            "invocations",
            "attempts",
            "human_requests",
            "codex_interactions",
            "human_decisions",
            "human_progress_intents",
            "waits",
            "outbox",
            "run_events",
            "artifacts",
            "external_artifact_sources",
            "inbox",
            "execution_host_sessions",
        }
        try:
            assert expected.issubset(set(inspect(engine).get_table_names()))
            with engine.connect() as connection:
                current = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                assert current == "0006_sqlite_import_receipts"
                assert connection.execute(
                    text("SELECT to_regclass('multiverse_storage_meta')")
                ).scalar_one() == "multiverse_storage_meta"
                assert connection.execute(
                    text(
                        "SELECT 1 FROM pg_indexes "
                        "WHERE schemaname = current_schema() "
                        "AND indexname = 'uq_commands_scope_key'"
                    )
                ).fetchone() is not None
                outbox_constraints = {
                    row[0]
                    for row in connection.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'outbox'::regclass"
                        )
                    )
                }
                assert "outbox_action_key_key" in outbox_constraints
                assert "outbox_attempt_id_key" not in outbox_constraints
        finally:
            engine.dispose()

        command.downgrade(config, "base")
        command.upgrade(config, "head")


def test_postgres_ledger_columns_cover_current_sqlite_ledger(tmp_path: Path) -> None:
    dsn = os.environ.get("MULTIVERSE_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for PostgreSQL schema parity tests")

    sqlite_ledger = Ledger(tmp_path / "ledger.db")
    try:
        sqlite_tables = {
            row["name"]: {
                column["name"]
                for column in sqlite_ledger._connection.execute(
                    f"PRAGMA table_info({row['name']})"
                ).fetchall()
            }
            for row in sqlite_ledger._connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    finally:
        sqlite_ledger.close()

    with _isolated_postgres_schema(dsn) as test_dsn:
        config = _alembic_config(test_dsn)
        command.upgrade(config, "head")
        engine = create_engine(test_dsn)
        try:
            inspector = inspect(engine)
            postgres_tables = {
                name: {column["name"] for column in inspector.get_columns(name)}
                for name in inspector.get_table_names()
                if name not in {"alembic_version", "multiverse_storage_meta"}
            }
            assert set(sqlite_tables).issubset(postgres_tables)
            for table, columns in sqlite_tables.items():
                assert columns.issubset(postgres_tables[table]), table
            assert postgres_tables["attempts"] - sqlite_tables["attempts"] == {
                "host_session_id"
            }
            assert {
                "inbox",
                "execution_host_sessions",
            }.issubset(postgres_tables.keys() - sqlite_tables.keys())
        finally:
            engine.dispose()


def test_postgres_ledger_constraints_cover_replay_and_references() -> None:
    dsn = os.environ.get("MULTIVERSE_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for PostgreSQL migration tests")

    with _isolated_postgres_schema(dsn) as test_dsn:
        config = _alembic_config(test_dsn)
        command.upgrade(config, "head")
        engine = create_engine(test_dsn)
        suffix = uuid.uuid4().hex
        run_id = f"run_{suffix}"
        scope_id = f"scope_{suffix}"
        invocation_id = f"inv_{suffix}"
        attempt_id = f"attempt_{suffix}"
        now = "2026-01-01T00:00:00Z"
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO runs "
                        "(id, namespace, workflow_id, package_digest, plan_json, input_json, "
                        "input_digest, status, control_mode, deadline_at, version, "
                        "created_at, updated_at) "
                        "VALUES (:id, 'local', 'delivery', 'sha256:pkg', '{}', '{}', "
                        "'sha256:input', 'queued', 'run', :deadline, 1, :now, :now)"
                    ),
                    {"id": run_id, "deadline": now, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO scopes "
                        "(id, run_id, workflow_id, path_json, input_json, input_digest, "
                        "status, created_at) "
                        "VALUES (:id, :run_id, 'delivery', '[]', '{}', 'sha256:input', "
                        "'active', :now)"
                    ),
                    {"id": scope_id, "run_id": run_id, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO invocations "
                        "(id, run_id, scope_id, node_id, status, input_json, input_digest, "
                        "version, created_at, updated_at) "
                        "VALUES (:id, :run_id, :scope_id, 'produce', 'queued', '{}', "
                        "'sha256:input', 1, :now, :now)"
                    ),
                    {"id": invocation_id, "run_id": run_id, "scope_id": scope_id, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO attempts "
                        "(id, run_id, scope_id, invocation_id, attempt_no, status, input_json, "
                        "input_digest, dispatch_key, effect_key, version, created_at, updated_at) "
                        "VALUES (:id, :run_id, :scope_id, :invocation_id, 1, 'queued', '{}', "
                        "'sha256:input', :dispatch, :effect, 1, :now, :now)"
                    ),
                    {
                        "id": attempt_id,
                        "run_id": run_id,
                        "scope_id": scope_id,
                        "invocation_id": invocation_id,
                        "dispatch": f"dispatch_{suffix}",
                        "effect": f"effect_{suffix}",
                        "now": now,
                    },
                )
                outbox_sql = text(
                    "INSERT INTO outbox "
                    "(id, action_key, namespace, run_id, scope_id, invocation_id, attempt_id, "
                    "action, payload_json, payload_digest, status, attempt_count, "
                    "created_at, updated_at) "
                    "VALUES (:id, :action_key, 'local', :run_id, :scope_id, :invocation_id, "
                    ":attempt_id, :action, '{}', 'sha256:payload', 'pending', 0, :now, :now)"
                )
                for action in ("submit", "cancel"):
                    connection.execute(
                        outbox_sql,
                        {
                            "id": f"outbox_{action}_{suffix}",
                            "action_key": f"{action}_{suffix}",
                            "run_id": run_id,
                            "scope_id": scope_id,
                            "invocation_id": invocation_id,
                            "attempt_id": attempt_id,
                            "action": action,
                            "now": now,
                        },
                    )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            outbox_sql,
                            {
                                "id": f"outbox_duplicate_{suffix}",
                                "action_key": f"submit_{suffix}",
                                "run_id": run_id,
                                "scope_id": scope_id,
                                "invocation_id": invocation_id,
                                "attempt_id": attempt_id,
                                "action": "submit",
                                "now": now,
                            },
                        )

                inbox_sql = text(
                    "INSERT INTO inbox "
                    "(id, namespace, executor, external_id, revision, payload_json, "
                    "payload_digest, received_at, status) "
                    "VALUES (:id, 'local', 'remote', :external_id, 1, '{}', "
                    "'sha256:payload', :now, 'pending')"
                )
                inbox_params = {
                    "id": f"inbox_{suffix}",
                    "external_id": f"external_{suffix}",
                    "now": now,
                }
                connection.execute(inbox_sql, inbox_params)
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            inbox_sql,
                            {**inbox_params, "id": f"inbox_duplicate_{suffix}"},
                        )

                for field in ("current_scope_id", "current_invocation_id"):
                    with pytest.raises(IntegrityError):
                        with connection.begin_nested():
                            connection.execute(
                                text(
                                    "INSERT INTO runs "
                                    "(id, namespace, workflow_id, package_digest, plan_json, "
                                    "input_json, input_digest, status, control_mode, deadline_at, "
                                    "version, created_at, updated_at, "
                                    f"{field}) "
                                    "VALUES (:id, 'local', 'delivery', 'sha256:pkg', '{}', '{}', "
                                    "'sha256:input', 'queued', 'run', :deadline, 1, :now, :now, "
                                    "'missing')"
                                ),
                                {
                                    "id": f"invalid_{field}_{suffix}",
                                    "deadline": now,
                                    "now": now,
                                },
                            )

                other_run_id = f"other_run_{suffix}"
                other_scope_id = f"other_scope_{suffix}"
                connection.execute(
                    text(
                        "INSERT INTO runs "
                        "(id, namespace, workflow_id, package_digest, plan_json, input_json, "
                        "input_digest, status, control_mode, deadline_at, version, "
                        "created_at, updated_at) "
                        "VALUES (:id, 'local', 'delivery', 'sha256:pkg', '{}', '{}', "
                        "'sha256:input', 'queued', 'run', :deadline, 1, :now, :now)"
                    ),
                    {"id": other_run_id, "deadline": now, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO scopes "
                        "(id, run_id, workflow_id, path_json, input_json, input_digest, "
                        "status, created_at) "
                        "VALUES (:id, :run_id, 'delivery', '[]', '{}', 'sha256:input', "
                        "'active', :now)"
                    ),
                    {"id": other_scope_id, "run_id": other_run_id, "now": now},
                )
                other_invocation_id = f"other_inv_{suffix}"
                connection.execute(
                    text(
                        "INSERT INTO invocations "
                        "(id, run_id, scope_id, node_id, status, input_json, input_digest, "
                        "version, created_at, updated_at) "
                        "VALUES (:id, :run_id, :scope_id, 'other', 'queued', '{}', "
                        "'sha256:input', 1, :now, :now)"
                    ),
                    {
                        "id": other_invocation_id,
                        "run_id": other_run_id,
                        "scope_id": other_scope_id,
                        "now": now,
                    },
                )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "UPDATE runs SET current_scope_id = :scope WHERE id = :run"
                            ),
                            {"scope": other_scope_id, "run": run_id},
                        )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "UPDATE runs SET current_invocation_id = :invocation "
                                "WHERE id = :run"
                            ),
                            {"invocation": other_invocation_id, "run": run_id},
                        )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "INSERT INTO invocations "
                                "(id, run_id, scope_id, node_id, status, input_json, "
                                "input_digest, version, created_at, updated_at) "
                                "VALUES (:id, :run, :other_scope, 'mismatch', 'queued', "
                                "'{}', 'sha256:input', 1, :now, :now)"
                            ),
                            {
                                "id": f"mismatch_inv_{suffix}",
                                "run": run_id,
                                "other_scope": other_scope_id,
                                "now": now,
                            },
                        )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "INSERT INTO attempts "
                                "(id, run_id, scope_id, invocation_id, attempt_no, status, "
                                "input_json, input_digest, dispatch_key, effect_key, version, "
                                "created_at, updated_at) "
                                "VALUES (:id, :run, :scope, :invocation, 2, 'queued', '{}', "
                                "'sha256:input', :dispatch, :effect, 1, :now, :now)"
                            ),
                            {
                                "id": f"mismatch_attempt_{suffix}",
                                "run": run_id,
                                "scope": scope_id,
                                "invocation": other_invocation_id,
                                "dispatch": f"mismatch_dispatch_{suffix}",
                                "effect": f"mismatch_effect_{suffix}",
                                "now": now,
                            },
                        )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "INSERT INTO scopes "
                                "(id, run_id, parent_scope_id, parent_invocation_id, "
                                "workflow_id, path_json, input_json, input_digest, status, "
                                "created_at) VALUES (:id, :run, :parent_scope, :parent_inv, "
                                "'delivery', '[]', '{}', 'sha256:input', 'active', :now)"
                            ),
                            {
                                "id": f"mismatch_child_scope_{suffix}",
                                "run": run_id,
                                "parent_scope": scope_id,
                                "parent_inv": other_invocation_id,
                                "now": now,
                            },
                        )

                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "INSERT INTO scopes "
                                "(id, run_id, parent_invocation_id, workflow_id, path_json, "
                                "input_json, input_digest, status, created_at) "
                                "VALUES (:id, :run_id, 'missing', 'delivery', '[]', '{}', "
                                "'sha256:input', 'active', :now)"
                            ),
                            {
                                "id": f"invalid_parent_{suffix}",
                                "run_id": run_id,
                                "now": now,
                            },
                        )

                session_id = f"host_session_{suffix}"
                session_sql = text(
                    "INSERT INTO execution_host_sessions "
                    "(id, namespace, host_id, provider, installation_identity, "
                    "native_session_id, version, metadata_json, created_at, updated_at) "
                    "VALUES (:id, 'local', 'host', 'codex', 'install', :native, "
                    "'1.0', '{}', :now, :now)"
                )
                session_params = {
                    "id": session_id,
                    "native": f"native_{suffix}",
                    "now": now,
                }
                connection.execute(session_sql, session_params)
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            session_sql,
                            {**session_params, "id": f"duplicate_session_{suffix}"},
                        )
                connection.execute(
                    text(
                        "UPDATE attempts SET host_session_id = :session "
                        "WHERE id = :attempt"
                    ),
                    {"session": session_id, "attempt": attempt_id},
                )
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            text(
                                "UPDATE attempts SET host_session_id = 'missing' "
                                "WHERE id = :attempt"
                            ),
                            {"attempt": attempt_id},
                        )
            with pytest.raises(RuntimeError, match="cannot downgrade"):
                command.downgrade(config, "0002_ledger_tables")
            with engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one() == "0006_sqlite_import_receipts"
        finally:
            engine.dispose()


def test_ownership_migration_downgrade_and_upgrade_preserves_valid_rows() -> None:
    dsn = os.environ.get("MULTIVERSE_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for PostgreSQL migration tests")

    with _isolated_postgres_schema(dsn) as test_dsn:
        config = _alembic_config(test_dsn)
        command.upgrade(config, "head")
        engine = create_engine(test_dsn)
        suffix = uuid.uuid4().hex
        now = "2026-01-01T00:00:00Z"
        run_id = f"valid_run_{suffix}"
        scope_id = f"valid_scope_{suffix}"
        invocation_id = f"valid_inv_{suffix}"
        attempt_id = f"valid_attempt_{suffix}"
        session_id = f"valid_session_{suffix}"
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO runs "
                        "(id, namespace, workflow_id, package_digest, plan_json, input_json, "
                        "input_digest, status, control_mode, deadline_at, version, "
                        "created_at, updated_at) "
                        "VALUES (:run, 'local', 'delivery', 'sha256:p', '{}', '{}', "
                        "'sha256:i', 'queued', 'run', :deadline, 1, :now, :now)"
                    ),
                    {
                        "run": run_id,
                        "scope": scope_id,
                        "invocation": invocation_id,
                        "deadline": now,
                        "now": now,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO scopes "
                        "(id, run_id, workflow_id, path_json, input_json, input_digest, "
                        "status, created_at) VALUES (:scope, :run, 'delivery', '[]', "
                        "'{}', 'sha256:i', 'active', :now)"
                    ),
                    {"scope": scope_id, "run": run_id, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO invocations "
                        "(id, run_id, scope_id, node_id, status, input_json, input_digest, "
                        "version, created_at, updated_at) VALUES (:inv, :run, :scope, "
                        "'produce', 'queued', '{}', 'sha256:i', 1, :now, :now)"
                    ),
                    {
                        "inv": invocation_id,
                        "run": run_id,
                        "scope": scope_id,
                        "now": now,
                    },
                )
                connection.execute(
                    text(
                        "UPDATE runs SET current_scope_id = :scope, "
                        "current_invocation_id = :invocation WHERE id = :run"
                    ),
                    {
                        "scope": scope_id,
                        "invocation": invocation_id,
                        "run": run_id,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO execution_host_sessions "
                        "(id, namespace, host_id, provider, installation_identity, "
                        "native_session_id, version, metadata_json, created_at, updated_at) "
                        "VALUES (:session, 'local', 'host', 'codex', 'install', "
                        "'native', '1', '{}', :now, :now)"
                    ),
                    {"session": session_id, "now": now},
                )
                connection.execute(
                    text(
                        "INSERT INTO attempts "
                        "(id, run_id, scope_id, invocation_id, attempt_no, status, "
                        "input_json, input_digest, dispatch_key, effect_key, version, "
                        "host_session_id, created_at, updated_at) VALUES (:attempt, :run, "
                        ":scope, :inv, 1, 'queued', '{}', 'sha256:i', 'dispatch', "
                        "'effect', 1, :session, :now, :now)"
                    ),
                    {
                        "attempt": attempt_id,
                        "run": run_id,
                        "scope": scope_id,
                        "inv": invocation_id,
                        "session": session_id,
                        "now": now,
                    },
                )
            command.downgrade(config, "0003_ledger_completeness")
            command.upgrade(config, "head")
            with engine.connect() as connection:
                assert connection.execute(
                    text("SELECT version_num FROM alembic_version")
                    ).scalar_one() == "0006_sqlite_import_receipts"
                assert connection.execute(
                    text("SELECT id FROM runs WHERE id = :run"),
                    {"run": run_id},
                ).scalar_one() == run_id
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


def test_alembic_offline_sql_uses_database_url_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(ROOT / "alembic.ini"), output_buffer=StringIO())
    monkeypatch.setenv("DATABASE_URL", "unsupporteddialect://offline/db")

    with pytest.raises(NoSuchModuleError):
        command.upgrade(config, "head", sql=True)

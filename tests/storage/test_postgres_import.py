from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.runtime.snapshot import export_sqlite_snapshot
from multiverse_workflow.storage.repository import PostgresLedgerRepository

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[2]


def _dsn() -> str:
    return os.environ.get("MULTIVERSE_POSTGRES_DSN", "")


def _isolated_dsn(dsn: str) -> tuple[str, str]:
    schema = f"mv_import_{os.urandom(8).hex()}"
    admin = create_engine(dsn)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = make_url(dsn).update_query_dict(
        {"options": f"-csearch_path={schema}"},
        append=True,
    ).render_as_string(hide_password=False)
    admin.dispose()
    return isolated, schema


def _migrate(dsn: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    command.upgrade(config, "head")


def test_postgres_imports_stopped_sqlite_control_plane_with_snapshot_proof(
    tmp_path: Path,
) -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL import test")

    sqlite_path = tmp_path / "source.db"
    ledger = Ledger(sqlite_path)
    try:
        run = ledger.create_queued_run(
            namespace="local",
            workflow_id="delivery",
            package_digest="sha256:package",
            binding_digest=None,
            plan={"entry": "produce"},
            input_value={"goal": "write"},
            deadline_at="2099-01-01T00:00:00Z",
            entry_node_id="produce",
            run_id="run-import",
        )
        scope_id = ledger.list_scopes(run["id"])[0]["id"]
        invocation = ledger.create_invocation(
            run_id=run["id"],
            scope_id=scope_id,
            node_id="produce",
            input_value={"goal": "write"},
        )
    finally:
        ledger.close()
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            "UPDATE runs SET current_invocation_id = ? WHERE id = ?",
            (invocation["id"], run["id"]),
        )
        connection.execute(
            """
            INSERT INTO scopes (
                id, run_id, parent_scope_id, workflow_id, path_json,
                input_json, input_digest, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "scope-child",
                run["id"],
                scope_id,
                "delivery",
                '["root","child"]',
                '{"goal":"write"}',
                "sha256:input",
                "active",
                "now",
            ),
        )

    snapshot = export_sqlite_snapshot(sqlite_path)
    isolated, schema = _isolated_dsn(dsn)
    admin = create_engine(dsn)
    try:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            imported = repository.import_sqlite_control_plane(
                sqlite_path,
                namespace="local",
                snapshot_digest=snapshot["snapshotDigest"],
            )
            assert imported["runCount"] == 1
            imported_run = repository.get_run("local", "run-import")
            assert imported_run["status"] == "queued"
            assert imported_run["current_scope_id"] == scope_id
            assert imported_run["current_invocation_id"] is not None
            child_scope = repository.get_scope("local", "scope-child")
            assert child_scope["parent_scope_id"] == scope_id
            assert repository.list_waits("local", "run-import") == [
                "run-start:run-import"
            ]
            assert repository.list_event_records("local", "run-import")[-1]["type"] == (
                "invocation.created"
            )
            replay = repository.import_sqlite_control_plane(
                sqlite_path,
                namespace="local",
                snapshot_digest=snapshot["snapshotDigest"],
            )
            assert replay == imported
        finally:
            repository.close()
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_import_rejects_snapshot_mismatch(tmp_path: Path) -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL import test")

    sqlite_path = tmp_path / "source.db"
    ledger = Ledger(sqlite_path)
    ledger.close()
    isolated, schema = _isolated_dsn(dsn)
    admin = create_engine(dsn)
    try:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            with pytest.raises(ValueError, match="snapshot digest"):
                repository.import_sqlite_control_plane(
                    sqlite_path,
                    namespace="local",
                    snapshot_digest="sha256:wrong",
                )
        finally:
            repository.close()
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_import_rejects_orphan_namespace_facts(tmp_path: Path) -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL import test")

    sqlite_path = tmp_path / "orphan.db"
    ledger = Ledger(sqlite_path)
    ledger.close()
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            """
            INSERT INTO commands (
                id, idempotency_key, fingerprint, operation, namespace,
                subject, resource_id, status, created_at, updated_at
            ) VALUES ('cmd-orphan', 'orphan', 'sha256:f', 'run.create',
                      'local', 'subject', 'run-missing', 'accepted', 'now', 'now')
            """
        )
    snapshot = export_sqlite_snapshot(sqlite_path)
    isolated, schema = _isolated_dsn(dsn)
    admin = create_engine(dsn)
    try:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            with pytest.raises(ValueError, match="without a Run"):
                repository.import_sqlite_control_plane(
                    sqlite_path,
                    namespace="local",
                    snapshot_digest=snapshot["snapshotDigest"],
                )
        finally:
            repository.close()
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()

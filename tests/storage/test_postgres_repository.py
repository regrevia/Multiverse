from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from multiverse_workflow.storage import repository as repository_module
from multiverse_workflow.storage.repository import PostgresLedgerRepository

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]


@contextmanager
def _isolated_dsn(dsn: str) -> Iterator[str]:
    schema = f"mv_repo_{uuid.uuid4().hex}"
    admin = create_engine(dsn)
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        isolated = make_url(dsn).update_query_dict(
            {"options": f"-csearch_path={schema}"},
            append=True,
        )
        yield isolated.render_as_string(hide_password=False)
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _dsn() -> str:
    return os.environ.get("MULTIVERSE_POSTGRES_DSN", "")


def _migrate(dsn: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    command.upgrade(config, "head")


def test_postgres_repository_creates_durable_queued_run() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            created = repository.create_queued_run(
                namespace="local",
                deployment_id="deployment_local",
                workflow_id="delivery",
                package_digest="sha256:package",
                binding_digest="sha256:binding",
                plan={"entry": "produce"},
                input_value={"goal": "write"},
                deadline_at="2099-01-01T00:00:00Z",
                entry_node_id="produce",
                run_id="run-repository-test",
            )
            assert created["status"] == "queued"
            assert created["current_node_id"] == "produce"
            assert created["current_scope_id"]

            reopened = PostgresLedgerRepository(isolated)
            try:
                loaded = reopened.get_run("local", "run-repository-test")
                assert loaded is not None
                assert loaded["input_json"] == '{"goal":"write"}'
                assert reopened.get_run("other", "run-repository-test") is None
                assert reopened.list_run_events("local", "run-repository-test") == [
                    "run.created",
                    "scope.created",
                ]
                assert reopened.list_run_events("other", "run-repository-test") == []
                assert reopened.list_waits("local", "run-repository-test") == [
                    "run-start:run-repository-test"
                ]
                assert reopened.list_waits("other", "run-repository-test") == []
            finally:
                reopened.close()
        finally:
            repository.close()


def test_postgres_repository_duplicate_run_id_rolls_back_second_write() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        kwargs = {
            "namespace": "local",
            "deployment_id": "deployment_local",
            "workflow_id": "delivery",
            "package_digest": "sha256:package",
            "binding_digest": None,
            "plan": {"entry": "produce"},
            "input_value": {"goal": "write"},
            "deadline_at": "2099-01-01T00:00:00Z",
            "entry_node_id": "produce",
            "run_id": "run-duplicate",
        }
        try:
            repository.create_queued_run(**kwargs)
            before_events = repository.list_run_events("local", "run-duplicate")
            before_scopes = repository.list_scope_ids("local", "run-duplicate")
            before_waits = repository.list_waits("local", "run-duplicate")
            with pytest.raises(IntegrityError):
                repository.create_queued_run(**kwargs)
            assert repository.get_run("local", "run-duplicate") is not None
            assert repository.list_run_events("local", "run-duplicate") == before_events
            assert repository.list_scope_ids("local", "run-duplicate") == before_scopes
            assert repository.list_waits("local", "run-duplicate") == before_waits
        finally:
            repository.close()


def test_postgres_repository_rolls_back_after_event_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        seed = PostgresLedgerRepository(isolated)
        try:
            seed.create_queued_run(
                namespace="local",
                deployment_id="deployment_local",
                workflow_id="seed",
                package_digest="sha256:seed",
                binding_digest=None,
                plan={"entry": "seed"},
                input_value={"goal": "seed"},
                deadline_at="2099-01-01T00:00:00Z",
                entry_node_id="seed",
                run_id="seed-run",
            )
            with seed._store.transaction() as connection:
                connection.execute(
                    text(
                        "INSERT INTO run_events "
                        "(id, run_id, seq, type, payload_json, occurred_at) "
                        "VALUES ('event-conflict', 'seed-run', 99, 'seed', '{}', :now)"
                    ),
                    {"now": "2026-01-01T00:00:00Z"},
                )
            original_new_id = repository_module._new_id

            event_calls = 0

            def conflicting_new_id(prefix: str) -> str:
                nonlocal event_calls
                if prefix == "event":
                    event_calls += 1
                if prefix == "event" and event_calls == 2:
                    return "event-conflict"
                return original_new_id(prefix)

            monkeypatch.setattr(repository_module, "_new_id", conflicting_new_id)
            with pytest.raises(IntegrityError):
                repository.create_queued_run(
                    namespace="local",
                    deployment_id="deployment_local",
                    workflow_id="delivery",
                    package_digest="sha256:package",
                    binding_digest=None,
                    plan={"entry": "produce"},
                    input_value={"goal": "write"},
                    deadline_at="2099-01-01T00:00:00Z",
                    entry_node_id="produce",
                    run_id="run-atomic-failure",
                )
            assert repository.get_run("local", "run-atomic-failure") is None
            assert repository.list_run_events("local", "run-atomic-failure") == []
            assert repository.list_scope_ids("local", "run-atomic-failure") == []
            assert repository.list_waits("local", "run-atomic-failure") == []
        finally:
            seed.close()
            repository.close()


def test_postgres_repository_creates_invocation_and_attempt_atomically() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            repository.create_queued_run(
                namespace="local",
                deployment_id=None,
                workflow_id="delivery",
                package_digest="sha256:package",
                binding_digest=None,
                plan={"entry": "produce"},
                input_value={"goal": "write"},
                deadline_at="2099-01-01T00:00:00Z",
                entry_node_id="produce",
                run_id="run-invocation",
            )
            invocation, attempt = repository.create_invocation_attempt(
                namespace="local",
                run_id="run-invocation",
                scope_id=repository.list_scope_ids("local", "run-invocation")[0],
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-invocation",
                effect_key="effect-invocation",
            )
            assert invocation["status"] == "planned"
            assert attempt["status"] == "created"
            assert attempt["attempt_no"] == 1
            assert repository.list_invocations("local", "run-invocation") == [
                invocation["id"]
            ]
            assert repository.list_attempts("local", "run-invocation") == [attempt["id"]]
        finally:
            repository.close()


def test_postgres_repository_rejects_attempt_scope_mismatch() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            repository.create_queued_run(
                namespace="local",
                deployment_id=None,
                workflow_id="delivery",
                package_digest="sha256:package",
                binding_digest=None,
                plan={"entry": "produce"},
                input_value={"goal": "write"},
                deadline_at="2099-01-01T00:00:00Z",
                entry_node_id="produce",
                run_id="run-scope-mismatch",
            )
            with pytest.raises(IntegrityError):
                repository.create_invocation_attempt(
                    namespace="local",
                    run_id="run-scope-mismatch",
                    scope_id="missing-scope",
                    node_id="produce",
                    input_value={"goal": "write"},
                    dispatch_key="dispatch-mismatch",
                    effect_key="effect-mismatch",
                )
            assert repository.list_invocations("local", "run-scope-mismatch") == []
        finally:
            repository.close()

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier

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


def test_postgres_repository_creates_submit_outbox_and_wait_idempotently() -> None:
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
                run_id="run-outbox",
            )
            scope_id = repository.list_scope_ids("local", "run-outbox")[0]
            _, attempt = repository.create_invocation_attempt(
                namespace="local",
                run_id="run-outbox",
                scope_id=scope_id,
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-outbox",
                effect_key="effect-outbox",
            )
            payload = {"goal": "write", "dispatchKey": "dispatch-outbox"}
            first = repository.ensure_submit_outbox(
                namespace="local",
                attempt_id=attempt["id"],
                payload=payload,
            )
            second = repository.ensure_submit_outbox(
                namespace="local",
                attempt_id=attempt["id"],
                payload=payload,
            )
            assert first["id"] == second["id"]
            assert first["action_key"] == f"submit:{attempt['id']}"
            assert repository.list_waits("local", "run-outbox")[-1] == (
                f"submit:{attempt['id']}"
            )
            assert repository.list_run_events("local", "run-outbox").count(
                "execution.submit_intent.created"
            ) == 1
            assert repository.list_waits("local", "run-outbox").count(
                f"submit:{attempt['id']}"
            ) == 1
        finally:
            repository.close()


def test_postgres_repository_rejects_submit_outbox_payload_conflict_and_wrong_namespace() -> None:
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
                run_id="run-outbox-conflict",
            )
            scope_id = repository.list_scope_ids("local", "run-outbox-conflict")[0]
            _, attempt = repository.create_invocation_attempt(
                namespace="local",
                run_id="run-outbox-conflict",
                scope_id=scope_id,
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-outbox-conflict",
                effect_key="effect-outbox-conflict",
            )
            payload = {"goal": "write", "dispatchKey": "dispatch-outbox-conflict"}
            repository.ensure_submit_outbox(
                namespace="local",
                attempt_id=attempt["id"],
                payload=payload,
            )
            with pytest.raises(IntegrityError, match="payload conflict"):
                repository.ensure_submit_outbox(
                    namespace="local",
                    attempt_id=attempt["id"],
                    payload={"goal": "changed"},
                )
            with pytest.raises(KeyError):
                repository.ensure_submit_outbox(
                    namespace="other",
                    attempt_id=attempt["id"],
                    payload=payload,
                )
            assert repository.list_run_events(
                "local", "run-outbox-conflict"
            ).count("execution.submit_intent.created") == 1
            assert repository.list_waits("local", "run-outbox-conflict").count(
                f"submit:{attempt['id']}"
            ) == 1
        finally:
            repository.close()


def test_postgres_repository_reactivates_cancelled_submit_wait() -> None:
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
                run_id="run-outbox-reactivate",
            )
            scope_id = repository.list_scope_ids("local", "run-outbox-reactivate")[0]
            _, attempt = repository.create_invocation_attempt(
                namespace="local",
                run_id="run-outbox-reactivate",
                scope_id=scope_id,
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-outbox-reactivate",
                effect_key="effect-outbox-reactivate",
            )
            payload = {"goal": "write"}
            outbox = repository.ensure_submit_outbox(
                namespace="local",
                attempt_id=attempt["id"],
                payload=payload,
            )
            with repository._store.transaction() as connection:
                connection.execute(
                    text(
                        "UPDATE waits SET status = 'cancelled' "
                        "WHERE namespace = :namespace AND wait_key = :wait_key"
                    ),
                    {
                        "namespace": "local",
                        "wait_key": f"submit:{attempt['id']}",
                    },
                )
            repository.ensure_submit_outbox(
                namespace="local",
                attempt_id=attempt["id"],
                payload=payload,
            )
            with repository._store.transaction() as connection:
                wait = connection.execute(
                    text(
                        "SELECT status, payload_json FROM waits "
                        "WHERE namespace = :namespace AND wait_key = :wait_key"
                    ),
                    {
                        "namespace": "local",
                        "wait_key": f"submit:{attempt['id']}",
                    },
                ).mappings().one()
            assert wait["status"] == "pending"
            assert json.loads(wait["payload_json"]) == {
                "outboxId": outbox["id"],
                "attemptId": attempt["id"],
            }
        finally:
            repository.close()


def test_postgres_repository_rolls_back_submit_outbox_on_event_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                run_id="run-outbox-rollback",
            )
            scope_id = repository.list_scope_ids("local", "run-outbox-rollback")[0]
            _, attempt = repository.create_invocation_attempt(
                namespace="local",
                run_id="run-outbox-rollback",
                scope_id=scope_id,
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-outbox-rollback",
                effect_key="effect-outbox-rollback",
            )
            original_insert_event = repository._insert_event

            def fail_submit_event(*args: object, **kwargs: object) -> None:
                if kwargs.get("event_type") == "execution.submit_intent.created":
                    raise RuntimeError("injected submit event failure")
                original_insert_event(*args, **kwargs)

            monkeypatch.setattr(repository, "_insert_event", fail_submit_event)
            with pytest.raises(RuntimeError, match="injected submit event failure"):
                repository.ensure_submit_outbox(
                    namespace="local",
                    attempt_id=attempt["id"],
                    payload={"goal": "write"},
                )
            assert repository.list_waits("local", "run-outbox-rollback") == [
                "run-start:run-outbox-rollback"
            ]
            assert repository.list_run_events("local", "run-outbox-rollback") == [
                "run.created",
                "scope.created",
                "invocation.created",
                "attempt.created",
            ]
        finally:
            repository.close()


def test_postgres_repository_serializes_event_sequences_for_concurrent_attempts(
) -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        seed = PostgresLedgerRepository(isolated)
        try:
            seed.create_queued_run(
                namespace="local",
                deployment_id=None,
                workflow_id="delivery",
                package_digest="sha256:package",
                binding_digest=None,
                plan={"entry": "produce"},
                input_value={"goal": "write"},
                deadline_at="2099-01-01T00:00:00Z",
                entry_node_id="produce",
                run_id="run-outbox-event-race",
            )
            scope_id = seed.list_scope_ids("local", "run-outbox-event-race")[0]
            attempts = [
                seed.create_invocation_attempt(
                    namespace="local",
                    run_id="run-outbox-event-race",
                    scope_id=scope_id,
                    node_id=f"produce-{index}",
                    input_value={"goal": f"write-{index}"},
                    dispatch_key=f"dispatch-event-race-{index}",
                    effect_key=f"effect-event-race-{index}",
                )[1]
                for index in range(2)
            ]
        finally:
            seed.close()

        barrier = Barrier(2)

        def submit(attempt_id: str) -> dict[str, object]:
            barrier.wait(timeout=5)
            repository = PostgresLedgerRepository(isolated)
            try:
                return repository.ensure_submit_outbox(
                    namespace="local",
                    attempt_id=attempt_id,
                    payload={"goal": attempt_id},
                )
            finally:
                repository.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, [attempt["id"] for attempt in attempts]))

        assert {result["attempt_id"] for result in results} == {
            attempt["id"] for attempt in attempts
        }
        verifier = PostgresLedgerRepository(isolated)
        try:
            with verifier._store.transaction() as connection:
                sequences = connection.execute(
                    text(
                        "SELECT seq FROM run_events WHERE run_id = :run_id "
                        "ORDER BY seq"
                    ),
                    {"run_id": "run-outbox-event-race"},
                ).scalars().all()
            assert sequences == list(range(1, len(sequences) + 1))
        finally:
            verifier.close()


def test_postgres_repository_submit_outbox_is_atomic_under_concurrent_calls(
) -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        seed = PostgresLedgerRepository(isolated)
        try:
            seed.create_queued_run(
                namespace="local",
                deployment_id=None,
                workflow_id="delivery",
                package_digest="sha256:package",
                binding_digest=None,
                plan={"entry": "produce"},
                input_value={"goal": "write"},
                deadline_at="2099-01-01T00:00:00Z",
                entry_node_id="produce",
                run_id="run-outbox-concurrent",
            )
            scope_id = seed.list_scope_ids("local", "run-outbox-concurrent")[0]
            _, attempt = seed.create_invocation_attempt(
                namespace="local",
                run_id="run-outbox-concurrent",
                scope_id=scope_id,
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-outbox-concurrent",
                effect_key="effect-outbox-concurrent",
            )
        finally:
            seed.close()

        barrier = Barrier(2)
        def submit() -> dict[str, object]:
            barrier.wait(timeout=5)
            repository = PostgresLedgerRepository(isolated)
            try:
                return repository.ensure_submit_outbox(
                    namespace="local",
                    attempt_id=attempt["id"],
                    payload={"goal": "write"},
                )
            finally:
                repository.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))

        assert results[0]["id"] == results[1]["id"]
        verifier = PostgresLedgerRepository(isolated)
        try:
            assert verifier.list_run_events(
                "local", "run-outbox-concurrent"
            ).count("execution.submit_intent.created") == 1
            assert verifier.list_waits("local", "run-outbox-concurrent").count(
                f"submit:{attempt['id']}"
            ) == 1
        finally:
            verifier.close()

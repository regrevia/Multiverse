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

from multiverse_workflow.runtime.wait_store import PostgresWaitStore
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
                assert [
                    item["id"]
                    for item in reopened.list_queued_runs(
                        namespace="local",
                        limit=10,
                    )
                ] == ["run-repository-test"]
                assert (
                    reopened.get_wait_by_key(
                        namespace="local",
                        wait_key="run-start:run-repository-test",
                    )
                    is not None
                )
                assert (
                    reopened.get_wait_by_key(
                        namespace="other",
                        wait_key="run-start:run-repository-test",
                    )
                    is None
                )
            finally:
                reopened.close()
        finally:
            repository.close()


def test_postgres_repository_persists_namespace_scoped_command_receipts() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            created = repository.create_command(
                namespace="local",
                subject="reviewer",
                operation="run.create",
                idempotency_key="command-1",
                fingerprint="sha256:fingerprint",
                resource_id="run-command-1",
                command_id="cmd-command-1",
            )
            assert created["status"] == "accepted"
            assert repository.get_command("local", "cmd-command-1")["id"] == (
                "cmd-command-1"
            )
            assert repository.get_command("other", "cmd-command-1") is None
            assert repository.get_command_by_key(
                namespace="local",
                subject="reviewer",
                operation="run.create",
                idempotency_key="command-1",
            )["id"] == "cmd-command-1"
            assert repository.list_commands_by_key(
                namespace="local",
                idempotency_key="command-1",
            )[0]["id"] == "cmd-command-1"

            completed = repository.finish_command(
                namespace="local",
                command_id="cmd-command-1",
                status="completed",
                resource_version=2,
            )
            assert completed["status"] == "completed"
            assert completed["resource_version"] == 2
            assert repository.finish_command(
                namespace="local",
                command_id="cmd-command-1",
                status="completed",
                resource_version=2,
            )["status"] == "completed"
            with pytest.raises(IntegrityError, match="terminal"):
                repository.finish_command(
                    namespace="local",
                    command_id="cmd-command-1",
                    status="rejected",
                    error={"code": "late"},
                )
            assert repository.get_command("local", "cmd-command-1")["status"] == (
                "completed"
            )
        finally:
            repository.close()


def test_postgres_repository_command_finish_has_one_concurrent_winner() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        seed = PostgresLedgerRepository(isolated)
        try:
            seed.create_command(
                namespace="local",
                subject="reviewer",
                operation="run.create",
                idempotency_key="command-race",
                fingerprint="sha256:fingerprint",
                resource_id="run-command-race",
                command_id="cmd-command-race",
            )
        finally:
            seed.close()

        barrier = Barrier(2)

        def finish(status: str) -> tuple[str, str]:
            repository = PostgresLedgerRepository(isolated)
            try:
                barrier.wait(timeout=5)
                record = repository.finish_command(
                    namespace="local",
                    command_id="cmd-command-race",
                    status=status,
                    resource_version=2 if status == "completed" else None,
                    error={"code": "rejected"} if status == "rejected" else None,
                )
                return ("ok", str(record["status"]))
            except IntegrityError:
                return ("conflict", status)
            finally:
                repository.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(finish, ["completed", "rejected"]))
        assert sorted(result[0] for result in results) == ["conflict", "ok"]


def test_postgres_repository_rejects_command_fingerprint_conflicts() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            repository.create_command(
                namespace="local",
                subject="reviewer",
                operation="run.create",
                idempotency_key="command-conflict",
                fingerprint="sha256:first",
                resource_id="run-first",
                command_id="cmd-first",
            )
            with pytest.raises(IntegrityError):
                repository.create_command(
                    namespace="local",
                    subject="reviewer",
                    operation="run.create",
                    idempotency_key="command-conflict",
                    fingerprint="sha256:second",
                    resource_id="run-second",
                    command_id="cmd-second",
                )
            assert repository.get_command("local", "cmd-second") is None
            assert repository.list_commands_by_key(
                namespace="local",
                idempotency_key="command-conflict",
            ) == [repository.get_command("local", "cmd-first")]
        finally:
            repository.close()


def test_postgres_repository_claims_completes_and_releases_waits() -> None:
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
                run_id="run-wait-contract",
            )
            waits = repository.list_wait_records(
                namespace="local",
                run_id="run-wait-contract",
            )
            assert len(waits) == 1
            wait_id = waits[0]["id"]
            due = repository.list_due_wait_records(
                namespace="local",
                now="9999-01-01T00:00:00Z",
            )
            assert [item["id"] for item in due] == [wait_id]
            claimed = repository.claim_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-1",
                now="9999-01-01T00:00:00Z",
            )
            assert claimed is not None
            assert claimed["status"] == "claimed"
            assert claimed["worker_id"] == "worker-1"
            assert (
                repository.claim_wait(
                    namespace="local",
                    wait_id=wait_id,
                    worker_id="worker-2",
                    now="9999-01-01T00:00:01Z",
                )
                is None
            )
            released = repository.release_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-1",
            )
            assert released["status"] == "pending"
            claimed_again = repository.claim_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-2",
                now="9999-01-01T00:00:02Z",
            )
            assert claimed_again is not None
            completed = repository.complete_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-2",
            )
            assert completed["status"] == "completed"
            assert repository.list_due_wait_records(
                namespace="local",
                now="9999-01-01T00:00:00Z",
            ) == []
        finally:
            repository.close()


def test_postgres_wait_store_implements_scheduler_contract() -> None:
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
                run_id="run-postgres-wait-store",
            )
            store = PostgresWaitStore(repository)
            waits = store.list_due_waits(
                namespace="local",
                now="9999-01-01T00:00:00Z",
                limit=10,
            )
            assert len(waits) == 1
            claimed = store.claim_wait(
                namespace="local",
                wait_id=waits[0]["id"],
                worker_id="worker-contract",
                now="9999-01-01T00:00:00Z",
            )
            assert claimed is not None
            assert store.reschedule_wait(
                namespace="local",
                wait_id=claimed["id"],
                worker_id="worker-contract",
                not_before="9999-01-01T00:00:01Z",
            )["status"] == "pending"
            claimed_again = store.claim_wait(
                namespace="local",
                wait_id=claimed["id"],
                worker_id="worker-contract",
                now="9999-01-01T00:00:02Z",
            )
            assert claimed_again is not None
            assert store.complete_wait(
                namespace="local",
                wait_id=claimed_again["id"],
                worker_id="worker-contract",
            )["status"] == "completed"
        finally:
            repository.close()


def test_postgres_repository_requeues_only_stale_waits_in_namespace() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set MULTIVERSE_POSTGRES_DSN for the PostgreSQL repository test")

    with _isolated_dsn(dsn) as isolated:
        _migrate(isolated)
        repository = PostgresLedgerRepository(isolated)
        try:
            for namespace, run_id in (("local", "run-stale-local"), ("other", "run-stale-other")):
                repository.create_queued_run(
                    namespace=namespace,
                    deployment_id=None,
                    workflow_id="delivery",
                    package_digest="sha256:package",
                    binding_digest=None,
                    plan={"entry": "produce"},
                    input_value={"goal": namespace},
                    deadline_at="2099-01-01T00:00:00Z",
                    entry_node_id="produce",
                    run_id=run_id,
                )
                wait_id = repository.list_wait_records(
                    namespace=namespace,
                    run_id=run_id,
                )[0]["id"]
                assert repository.claim_wait(
                        namespace=namespace,
                        wait_id=wait_id,
                        worker_id=f"{namespace}-worker",
                        now="9999-01-01T00:00:00Z",
                )
            with repository._store.transaction() as connection:
                connection.execute(
                    text(
                        "UPDATE waits SET claimed_at = :claimed_at "
                        "WHERE wait_key IN ('run-start:run-stale-local', "
                        "'run-start:run-stale-other')"
                    ),
                    {"claimed_at": "2026-10-05T00:00:00Z"},
                )
            assert (
                repository.requeue_stale_waits(
                    namespace="local",
                    older_than="2026-10-06T00:00:00Z",
                    now="2026-10-06T00:01:00Z",
                )
                == 1
            )
            assert repository.list_wait_records(
                namespace="local",
                run_id="run-stale-local",
                statuses=("pending",),
            )[0]["status"] == "pending"
            assert repository.list_wait_records(
                namespace="other",
                run_id="run-stale-other",
                statuses=("claimed",),
            )[0]["status"] == "claimed"
        finally:
            repository.close()


def test_postgres_repository_claim_wait_has_one_concurrent_winner() -> None:
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
                run_id="run-wait-race",
            )
            wait_id = seed.list_wait_records(
                namespace="local",
                run_id="run-wait-race",
            )[0]["id"]
        finally:
            seed.close()

        barrier = Barrier(2)

        def claim(worker_id: str) -> dict[str, object] | None:
            barrier.wait(timeout=5)
            repository = PostgresLedgerRepository(isolated)
            try:
                return repository.claim_wait(
                    namespace="local",
                    wait_id=wait_id,
                    worker_id=worker_id,
                    now="9999-01-01T00:00:00Z",
                )
            finally:
                repository.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ["worker-1", "worker-2"]))

        assert sum(result is not None for result in results) == 1
        winner = next(result for result in results if result is not None)
        assert winner["status"] == "claimed"
        assert winner["worker_id"] in {"worker-1", "worker-2"}


def test_postgres_repository_stale_worker_cannot_complete_or_release_new_claim(
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
                run_id="run-wait-fencing",
            )
            wait_id = repository.list_wait_records(
                namespace="local",
                run_id="run-wait-fencing",
            )[0]["id"]
            assert repository.claim_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-old",
                now="9999-01-01T00:00:00Z",
            )
            assert (
                repository.requeue_stale_waits(
                    namespace="local",
                    older_than="9998-12-31T23:59:59Z",
                    now="9999-01-01T00:00:02Z",
                )
                == 0
            )
            with repository._store.transaction() as connection:
                connection.execute(
                    text(
                        "UPDATE waits SET claimed_at = :claimed_at "
                        "WHERE id = :wait_id"
                    ),
                    {
                        "claimed_at": "2026-10-05T00:00:00Z",
                        "wait_id": wait_id,
                    },
                )
            assert (
                repository.requeue_stale_waits(
                    namespace="local",
                    older_than="2026-10-06T00:00:00Z",
                    now="2026-10-06T00:01:00Z",
                )
                == 1
            )
            assert repository.claim_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-new",
                now="9999-01-01T00:00:00Z",
            )
            with pytest.raises(ValueError, match="worker"):
                repository.complete_wait(
                    namespace="local",
                    wait_id=wait_id,
                    worker_id="worker-old",
                )
            with pytest.raises(ValueError, match="worker"):
                repository.release_wait(
                    namespace="local",
                    wait_id=wait_id,
                    worker_id="worker-old",
                )
            assert repository.complete_wait(
                namespace="local",
                wait_id=wait_id,
                worker_id="worker-new",
            )["status"] == "completed"
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


def test_postgres_repository_updates_run_with_optimistic_version_and_event() -> None:
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
                run_id="run-update-contract",
            )
            updated = repository.update_run(
                namespace="local",
                run_id="run-update-contract",
                expected_version=1,
                status="running",
                control_mode="run",
                current_node_id="produce",
                output=None,
                error=None,
            )
            assert updated["status"] == "running"
            assert updated["version"] == 2
            assert updated["output_json"] is None
            assert updated["error_json"] is None
            assert repository.list_run_events(
                "local", "run-update-contract"
            ) == [
                "run.created",
                "scope.created",
                "run.updated",
            ]
            scope_id = repository.list_scope_ids(
                "local", "run-update-contract"
            )[0]
            invocation, _attempt = repository.create_invocation_attempt(
                namespace="local",
                run_id="run-update-contract",
                scope_id=scope_id,
                node_id="produce",
                input_value={"goal": "write"},
                dispatch_key="dispatch-run-update",
                effect_key="effect-run-update",
            )
            with repository._store.transaction() as connection:
                connection.execute(
                    text(
                        "UPDATE runs SET current_invocation_id = :invocation_id "
                        "WHERE id = :run_id"
                    ),
                    {
                        "invocation_id": invocation["id"],
                        "run_id": "run-update-contract",
                    },
                )
            with repository._store.transaction() as connection:
                connection.execute(
                    text(
                        "UPDATE runs SET version = 3 "
                        "WHERE id = :run_id"
                    ),
                    {"run_id": "run-update-contract"},
                )
            with pytest.raises(ValueError, match="version"):
                repository.update_run(
                    namespace="local",
                    run_id="run-update-contract",
                    expected_version=2,
                    status="failed",
                    control_mode="run",
                    current_node_id="produce",
                    output=None,
                    error={"code": "stale"},
                )
            encoded = repository.update_run(
                namespace="local",
                run_id="run-update-contract",
                expected_version=3,
                status="failed",
                control_mode="run",
                current_node_id="produce",
                output={"result": "done"},
                error={"code": "EXAMPLE"},
            )
            assert json.loads(encoded["output_json"]) == {"result": "done"}
            assert json.loads(encoded["error_json"]) == {"code": "EXAMPLE"}

            moved = repository.update_run(
                namespace="local",
                run_id="run-update-contract",
                expected_version=4,
                status="running",
                control_mode="run",
                current_node_id="next-node",
                output=None,
                error=None,
            )
            assert moved["current_node_id"] == "next-node"
            assert moved["current_invocation_id"] is None
        finally:
            repository.close()


def test_postgres_repository_run_update_has_one_concurrent_version_winner() -> None:
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
                run_id="run-update-race",
            )
        finally:
            seed.close()

        barrier = Barrier(2)

        def update(status: str) -> tuple[str, str]:
            repository = PostgresLedgerRepository(isolated)
            try:
                barrier.wait(timeout=5)
                result = repository.update_run(
                    namespace="local",
                    run_id="run-update-race",
                    expected_version=1,
                    status=status,
                    control_mode="run",
                    current_node_id="produce",
                    output=None,
                    error=None,
                )
                return ("ok", str(result["status"]))
            except ValueError:
                return ("conflict", status)
            finally:
                repository.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, ["running", "paused"]))
        assert sorted(item[0] for item in results) == ["conflict", "ok"]


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


def test_postgres_repository_run_update_rolls_back_on_event_failure(
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
                run_id="run-update-rollback",
            )
            original_insert_event = repository._insert_event

            def fail_update_event(*args: object, **kwargs: object) -> None:
                if kwargs.get("event_type") == "run.updated":
                    raise RuntimeError("injected run update event failure")
                original_insert_event(*args, **kwargs)

            monkeypatch.setattr(repository, "_insert_event", fail_update_event)
            with pytest.raises(RuntimeError, match="run update event failure"):
                repository.update_run(
                    namespace="local",
                    run_id="run-update-rollback",
                    expected_version=1,
                    status="running",
                    control_mode="run",
                    current_node_id="produce",
                    output={"result": "not committed"},
                    error=None,
                )
            run = repository.get_run("local", "run-update-rollback")
            assert run is not None
            assert run["status"] == "queued"
            assert run["version"] == 1
            assert run["output_json"] is None
            assert repository.list_run_events(
                "local", "run-update-rollback"
            ) == ["run.created", "scope.created"]
        finally:
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

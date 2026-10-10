from __future__ import annotations

import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry
from multiverse_workflow.runtime.runner import Runner

ROOT = Path(__file__).parents[2]


def test_codex_interaction_is_versioned_authorized_and_idempotent(tmp_path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        deployment_id=None,
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={"workflowId": "delivery"},
        input_value={"goal": "test"},
        deadline_at="2099-01-01T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"], input_value={"goal": "test"})
    invocation = ledger.create_invocation(run["id"], scope["id"], "produce", {"goal": "test"})
    attempt = ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "test"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )

    interaction = ledger.create_codex_interaction(
        run_id=run["id"],
        scope_id=scope["id"],
        invocation_id=invocation["id"],
        attempt_id=attempt["id"],
        native_request_id="req-1",
        thread_id="thread-1",
        turn_id="turn-1",
        kind="item/tool/requestUserInput",
        payload={"questions": [{"id": "choice", "question": "Continue?"}]},
        authorized_subjects=["operator"],
        expires_at="2099-01-01T00:01:00Z",
    )
    repeated_interaction = ledger.create_codex_interaction(
        run_id=run["id"],
        scope_id=scope["id"],
        invocation_id=invocation["id"],
        attempt_id=attempt["id"],
        native_request_id="req-1",
        thread_id="thread-1",
        turn_id="turn-1",
        kind="item/tool/requestUserInput",
        payload={"questions": [{"id": "choice", "question": "Continue?"}]},
        authorized_subjects=["operator"],
        expires_at="2099-01-01T00:01:00Z",
    )
    assert repeated_interaction["id"] == interaction["id"]
    assert repeated_interaction["kind"] == "item/tool/requestUserInput"

    replied = ledger.respond_codex_interaction(
        interaction["id"],
        expected_version=interaction["version"],
        actor="operator",
        response={"answers": {"choice": "yes"}},
        idempotency_key="reply-1",
    )
    assert replied["status"] == "replied"
    assert replied["version"] == 2

    repeated = ledger.respond_codex_interaction(
        interaction["id"],
        expected_version=1,
        actor="operator",
        response={"answers": {"choice": "yes"}},
        idempotency_key="reply-1",
    )
    assert repeated["id"] == interaction["id"]

    ledger.invalidate_codex_interactions_for_attempt(
        attempt["id"], reason="native response outcome is unknown after restart"
    )
    invalidated_replay = ledger.respond_codex_interaction(
        interaction["id"],
        expected_version=1,
        actor="operator",
        response={"answers": {"choice": "yes"}},
        idempotency_key="reply-1",
    )
    assert invalidated_replay["status"] == "invalid"
    with pytest.raises(LedgerConflict, match="idempotency key was reused"):
        ledger.respond_codex_interaction(
            interaction["id"],
            expected_version=1,
            actor="operator",
            response={"answers": {"choice": "no"}},
            idempotency_key="reply-1",
        )

    with pytest.raises(LedgerConflict, match="invalid"):
        ledger.respond_codex_interaction(
            interaction["id"],
            expected_version=3,
            actor="operator",
            response={"answers": {"choice": "yes"}},
            idempotency_key="reply-stale-version",
        )

    with pytest.raises(LedgerConflict, match="authorized"):
        ledger.create_codex_interaction(
            run_id=run["id"],
            scope_id=scope["id"],
            invocation_id=invocation["id"],
            attempt_id=attempt["id"],
            native_request_id="req-2",
            thread_id="thread-1",
            turn_id="turn-1",
            kind="item/commandExecution/requestApproval",
            payload={},
            authorized_subjects=[],
            expires_at="2099-01-01T00:01:00Z",
        )

    unauthorized = ledger.create_codex_interaction(
        run_id=run["id"],
        scope_id=scope["id"],
        invocation_id=invocation["id"],
        attempt_id=attempt["id"],
        native_request_id="req-unauthorized",
        thread_id="thread-1",
        turn_id="turn-1",
        kind="item/commandExecution/requestApproval",
        payload={"command": "write"},
        authorized_subjects=["operator"],
        expires_at="2099-01-01T00:01:00Z",
    )
    with pytest.raises(LedgerConflict, match="authorized"):
        ledger.respond_codex_interaction(
            unauthorized["id"],
            expected_version=unauthorized["version"],
            actor="another-user",
            response={"decision": "accept"},
            idempotency_key="reply-unauthorized",
        )

    expired = ledger.create_codex_interaction(
        run_id=run["id"],
        scope_id=scope["id"],
        invocation_id=invocation["id"],
        attempt_id=attempt["id"],
        native_request_id="req-expired",
        thread_id="thread-1",
        turn_id="turn-1",
        kind="item/commandExecution/requestApproval",
        payload={"command": "write"},
        authorized_subjects=["operator"],
        expires_at="2000-01-01T00:00:00Z",
    )
    with pytest.raises(LedgerConflict, match="expired"):
        ledger.respond_codex_interaction(
            expired["id"],
            expected_version=expired["version"],
            actor="operator",
            response={"decision": "accept"},
            idempotency_key="reply-expired",
        )
    assert ledger.get_codex_interaction(expired["id"])["status"] == "expired"


def test_native_request_waits_for_persisted_human_reply(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runner.db",
    )
    original_drive = runner._drive
    runner._drive = lambda run_id, scope_id, node_id: runner.ledger.get_run(run_id)  # type: ignore[method-assign,return-value]
    try:
        run = runner.start({"goal": "review a candidate"})
    finally:
        runner._drive = original_drive  # type: ignore[method-assign]
    scope = runner.ledger.list_scopes(run["id"])[0]
    invocation = runner.ledger.create_invocation(
        run["id"], scope["id"], "produce", {"goal": "review a candidate"}
    )
    attempt = runner.ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "review a candidate"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )
    expires_at = (datetime.now(UTC) + timedelta(seconds=10)).isoformat().replace(
        "+00:00", "Z"
    )
    worker_runner: list[Runner] = []
    returned: list[dict] = []
    failure: list[BaseException] = []

    def wait_for_reply() -> None:
        active_runner = Runner(
            ROOT / "presets/content-delivery",
            binding_path=ROOT / "examples/bindings/content-local.yaml",
            database_path=tmp_path / "runner.db",
        )
        worker_runner.append(active_runner)
        try:
            returned.append(
                active_runner._wait_for_codex_interaction(
                    run_id=run["id"],
                    scope_id=scope["id"],
                    invocation=invocation,
                    attempt=attempt,
                    binding_config={"interactionAuthorizedSubjects": ["operator"]},
                    request_id="native-approval-1",
                    kind="item/commandExecution/requestApproval",
                    payload={
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "command": "pytest",
                    },
                    expires_at=expires_at,
                )
            )
        except BaseException as exc:
            failure.append(exc)
        finally:
            active_runner.close()

    worker = threading.Thread(target=wait_for_reply)
    worker.start()
    deadline = time.monotonic() + 3
    interactions = []
    while time.monotonic() < deadline:
        interactions = runner.ledger.list_codex_interactions(run_id=run["id"])
        if interactions:
            break
        time.sleep(0.01)
    assert interactions, repr(failure)
    interaction = interactions[0]
    assert interaction["status"] == "pending"

    runner.ledger.respond_codex_interaction(
        interaction["id"],
        expected_version=interaction["version"],
        actor="operator",
        response={"decision": "accept"},
        idempotency_key="native-approval-reply-1",
    )
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert not failure
    assert returned == [{"decision": "accept"}]


@pytest.mark.parametrize("confirm_stop", [True, False])
def test_runner_cancel_interrupts_and_confirms_codex_turn(
    tmp_path: Path, confirm_stop: bool
) -> None:
    app_server = tmp_path / "fake_codex_cancel.py"
    turn_started = tmp_path / "turn-started"
    interrupt_received = tmp_path / "interrupt-received"
    app_server.write_text(
        "import json, pathlib, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    request_id = request.get('id')\n"
        "    if request_id == 1:\n"
        "        print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
        "    elif request_id == 2:\n"
        "        print(json.dumps({'id': 2, 'result': "
        "{'thread': {'id': 'thread-1'}}}), flush=True)\n"
        "    elif request_id == 3:\n"
        f"        pathlib.Path({str(turn_started)!r}).touch()\n"
        "        print(json.dumps({'id': 3, 'result': {'turn': {'id': 'turn-1'}}}), flush=True)\n"
        "    elif request_id == 4:\n"
        "        assert request['method'] == 'turn/interrupt'\n"
        f"        pathlib.Path({str(interrupt_received)!r}).touch()\n"
        "        print(json.dumps({'id': 4, 'result': {}}), flush=True)\n"
        + (
            "        print(json.dumps({'method': 'turn/completed', "
            "'params': {'turn': {'status': 'interrupted'}}}), flush=True)\n"
            if confirm_stop
            else ""
        ),
        encoding="utf-8",
    )
    binding_data = YAML(typ="safe").load(
        (ROOT / "examples/bindings/content-local.yaml").read_text(encoding="utf-8")
    )
    producer = binding_data["spec"]["slots"]["producer"]
    producer["adapter"] = "codex"
    producer["executorRef"] = "builtin.codex-deliverable.v1"
    producer["config"] = {
        "cwd": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(tmp_path),
        "model": "test-model",
        "command": [sys.executable, "-u", str(app_server)],
        "timeoutSeconds": 10,
        "interactionAuthorizedSubjects": ["operator"],
    }
    binding_path = tmp_path / "binding.yaml"
    with binding_path.open("w", encoding="utf-8") as handle:
        YAML().dump(binding_data, handle)
    registry = ExecutorRegistry(
        [
            replace(descriptor, verified=True, supports_cancel=True)
            if descriptor.executor_ref == "builtin.codex-deliverable.v1"
            else descriptor
            for descriptor in local_executor_registry().descriptors()
        ]
    )
    database_path = tmp_path / "runtime.db"
    controller = Runner(
        ROOT / "presets/content-delivery",
        binding_path=binding_path,
        database_path=database_path,
        executor_registry=registry,
    )
    created_run: list[dict] = []
    start_result: list[dict] = []
    start_error: list[BaseException] = []

    def start_run() -> None:
        worker_runner = Runner(
            ROOT / "presets/content-delivery",
            binding_path=binding_path,
            database_path=database_path,
            executor_registry=registry,
        )
        create_run = worker_runner.ledger.create_run

        def capture_run(*args, **kwargs):
            result = create_run(*args, **kwargs)
            created_run.append(result)
            return result

        worker_runner.ledger.create_run = capture_run  # type: ignore[method-assign]
        try:
            start_result.append(
                worker_runner.start({"goal": "wait for a cancellation signal"})
            )
        except BaseException as exc:
            start_error.append(exc)
        finally:
            worker_runner.close()

    worker = threading.Thread(target=start_run)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not turn_started.exists():
            time.sleep(0.01)
        assert not start_error, repr(start_error)
        assert turn_started.exists()
        assert created_run
        run = controller.ledger.get_run(created_run[0]["id"])
        assert run is not None

        requested = controller.cancel(
            run["id"],
            expected_version=run["version"],
            reason="operator requested stop",
        )
        assert requested["status"] == "stopping"
        worker.join(timeout=8)

        assert not worker.is_alive()
        assert not start_error
        assert interrupt_received.exists()
        assert start_result[0]["status"] == (
            "cancelled" if confirm_stop else "blocked"
        )
        attempts = controller.ledger.list_attempts(run["id"])
        assert len(attempts) == 1
        assert attempts[0]["status"] == (
            "cancelled" if confirm_stop else "unknown"
        )
    finally:
        if worker.is_alive():
            worker.join(timeout=6)
        controller.close()


def test_permission_escalation_interaction_is_fail_closed(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runner.db",
    )
    original_drive = runner._drive
    runner._drive = lambda run_id, scope_id, node_id: runner.ledger.get_run(run_id)  # type: ignore[method-assign,return-value]
    try:
        run = runner.start({"goal": "write a release note"})
    finally:
        runner._drive = original_drive  # type: ignore[method-assign]
    scope = runner.ledger.list_scopes(run["id"])[0]
    invocation = runner.ledger.create_invocation(
        run["id"], scope["id"], "produce", {"goal": "write a release note"}
    )
    attempt = runner.ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "write a release note"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )

    with pytest.raises(Exception, match="unsupported Codex interaction"):
        runner._wait_for_codex_interaction(
            run_id=run["id"],
            scope_id=scope["id"],
            invocation=invocation,
            attempt=attempt,
            binding_config={"interactionAuthorizedSubjects": ["operator"]},
            request_id="native-permission-1",
            kind="item/permissions/requestApproval",
            payload={"threadId": "thread-1", "turnId": "turn-1"},
            expires_at="2099-01-01T00:00:00Z",
        )

    interaction = runner.ledger.list_codex_interactions(run_id=run["id"])[0]
    assert interaction["status"] == "invalid"

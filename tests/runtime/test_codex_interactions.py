from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
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

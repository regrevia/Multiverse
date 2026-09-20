from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.runtime.runner import Runner
from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.service.contracts import (
    AttemptReconcileRequest,
    HumanDecisionRequest,
    RunCreateRequest,
)

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
BINDING = ROOT / "examples/bindings/content-local.yaml"


def _runner(tmp_path: Path) -> Runner:
    return Runner(
        PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
    )


def _application(tmp_path: Path) -> RuntimeApplication:
    return RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )


def _request() -> RunCreateRequest:
    return RunCreateRequest(
        deploymentId="deployment_local",
        workflowId="delivery",
        input={"goal": "write a release note"},
    )


def _unknown_producer_attempt(
    application: RuntimeApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, dict[str, object], dict[str, object]]:
    created = application.create_run(_request(), idempotency_key="create-reconcile")
    original_drive = application.runner._drive
    monkeypatch.setattr(
        application.runner,
        "_drive",
        lambda run_id, scope_id, node_id: application.runner.ledger.get_run(run_id),
    )
    try:
        application.runner.sweep(worker_id="test-worker")
    finally:
        monkeypatch.setattr(application.runner, "_drive", original_drive)
    scope = application.runner.ledger.list_scopes(created.resource_id)[0]
    invocation = application.runner.ledger.create_invocation(
        created.resource_id,
        scope["id"],
        "produce",
        {"goal": "write a release note"},
    )
    application.runner.ledger.finish_invocation(invocation["id"], status="running")
    attempt = application.runner.ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "write a release note"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )
    application.runner.ledger.finish_attempt(attempt["id"], status="running")
    unknown = application.runner.ledger.finish_attempt(attempt["id"], status="unknown")
    application.runner.ledger.update_run(
        created.resource_id,
        status="running",
        current_scope_id=scope["id"],
        current_node_id="produce",
        current_invocation_id=None,
    )
    return created.resource_id, invocation, unknown


def test_enqueue_persists_a_queued_run_until_a_worker_sweeps_it(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    queued = runner.enqueue(
        {"goal": "write a release note"},
        workflow_id="delivery",
    )

    assert queued["status"] == "queued"
    assert runner.ledger.list_invocations(queued["id"]) == []
    start_wait = runner.ledger.get_wait_by_key(
        "local", f"run-start:{queued['id']}"
    )
    assert start_wait is not None
    assert start_wait["status"] == "pending"

    results = runner.sweep(worker_id="test-worker")

    assert results[0]["kind"] == "run-start"
    assert runner.ledger.get_run(queued["id"])["status"] == "waiting"
    assert runner.ledger.get_wait(start_wait["id"])["status"] == "completed"


def test_service_create_does_not_drive_workflow_on_request_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path)

    def fail_if_driven(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("HTTP service must not drive a workflow")

    monkeypatch.setattr(application.runner, "_drive", fail_if_driven)

    receipt = application.create_run(_request(), idempotency_key="create-async")

    assert receipt.status == "completed"
    assert application.get_run("local", receipt.resource_id)["status"] == "queued"


def test_human_decision_is_persisted_before_worker_continuation(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    created = application.create_run(_request(), idempotency_key="create-async")
    application.runner.sweep(worker_id="test-worker")
    pending = application.runner.pending_human_requests(created.resource_id)[0]

    decided = application.decide_human_request(
        "local",
        pending["id"],
        HumanDecisionRequest(
            expectedVersion=pending["version"],
            subjectDigest=pending["subject_digest"],
            choice="approve",
            comment="Approved.",
        ),
        idempotency_key="decision-async",
    )

    assert decided.status == "completed"
    assert application.get_run("local", created.resource_id)["status"] == "waiting"
    progress_wait = application.runner.ledger.get_wait_by_key(
        "local", f"human-progress:{pending['id']}"
    )
    assert progress_wait is not None
    assert progress_wait["status"] == "pending"

    application.runner.sweep(worker_id="test-worker")

    assert application.get_run("local", created.resource_id)["status"] == "succeeded"


def test_repeated_async_create_returns_the_same_queued_run(tmp_path: Path) -> None:
    application = _application(tmp_path)

    first = application.create_run(_request(), idempotency_key="create-async")
    second = application.create_run(_request(), idempotency_key="create-async")

    assert second.resource_id == first.resource_id
    assert len(application.runner.ledger.list_scopes(first.resource_id)) == 1
    assert len(application.runner.ledger.list_waits(run_id=first.resource_id)) == 1


def test_service_reconcile_persists_a_worker_wake_without_driving_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path)
    run_id, _invocation, unknown = _unknown_producer_attempt(application, monkeypatch)

    def fail_if_applied(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("HTTP reconciliation must not apply workflow progress")

    monkeypatch.setattr(application.runner, "_apply_reconciled_attempt", fail_if_applied)

    receipt = application.reconcile_attempt(
        "local",
        unknown["id"],
        AttemptReconcileRequest(
            expectedVersion=unknown["version"],
            conclusion="confirmed_failed",
            evidenceRefs=["evidence://provider/failed"],
            reason="The provider confirmed the execution failed.",
        ),
        idempotency_key="reconcile-async",
    )

    assert receipt.status == "completed"
    assert application.get_run("local", run_id)["status"] == "running"
    wait = application.runner.ledger.get_wait_by_key(
        "local", f"attempt-reconcile:{unknown['id']}"
    )
    assert wait is not None
    assert wait["kind"] == "attempt-reconcile"
    assert wait["status"] == "pending"


def test_worker_applies_a_persisted_attempt_reconciliation_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path)
    run_id, _invocation, unknown = _unknown_producer_attempt(application, monkeypatch)

    application.reconcile_attempt(
        "local",
        unknown["id"],
        AttemptReconcileRequest(
            expectedVersion=unknown["version"],
            conclusion="confirmed_failed",
            evidenceRefs=["evidence://provider/failed"],
            reason="The provider confirmed the execution failed.",
        ),
        idempotency_key="reconcile-async",
    )

    results = application.runner.sweep(worker_id="test-worker")

    assert results[0]["kind"] == "attempt-reconcile"
    assert application.get_run("local", run_id)["status"] == "failed"
    assert application.runner.ledger.get_wait_by_key(
        "local", f"attempt-reconcile:{unknown['id']}"
    )["status"] == "completed"
    assert len(application.runner.ledger.list_attempts(run_id)) == 1

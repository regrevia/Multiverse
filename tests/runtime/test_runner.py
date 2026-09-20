import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from multiverse_workflow.runtime.executors import (
    ExecutionResult,
    ExecutorError,
    GeneratedArtifact,
)
from multiverse_workflow.runtime.ledger import LedgerConflict
from multiverse_workflow.runtime.projection import build_run_projection
from multiverse_workflow.runtime.registry import (
    ExecutorDescriptor,
    ExecutorRegistry,
    local_executor_registry,
)
from multiverse_workflow.runtime.runner import RunError, Runner

ROOT = Path(__file__).parents[2]


def _start_with_unknown_producer_attempt(runner: Runner) -> tuple[dict, dict, dict]:
    drive = runner._drive
    runner._drive = lambda run_id, scope_id, node_id: runner.ledger.get_run(run_id)  # type: ignore[method-assign,return-value]
    try:
        run = runner.start({"goal": "write a release note"})
    finally:
        runner._drive = drive  # type: ignore[method-assign]
    scope = runner.ledger.list_scopes(run["id"])[0]
    invocation = runner.ledger.create_invocation(
        run["id"],
        scope["id"],
        "produce",
        {"goal": "write a release note"},
    )
    runner.ledger.finish_invocation(invocation["id"], status="running")
    attempt = runner.ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "write a release note"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )
    runner.ledger.finish_attempt(attempt["id"], status="running")
    unknown = runner.ledger.finish_attempt(attempt["id"], status="unknown")
    runner.ledger.update_run(
        run["id"],
        status="running",
        current_node_id="produce",
    )
    return run, invocation, unknown


def test_content_delivery_waits_for_review_and_finishes_after_approval(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    waiting = runner.start({"goal": "write a release note"})

    assert waiting["status"] == "waiting"
    request = runner.pending_human_requests()[0]
    assert request["status"] == "pending"
    assert json.loads(request["input_json"])["deliverable"]["text"]

    finished = runner.decide(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
    )

    assert finished["status"] == "succeeded"
    output = json.loads(finished["output_json"])
    assert output["review"]["decision"] == "approve"
    assert output["deliverable"]["artifact_refs"] == []


def test_content_delivery_rejection_follows_explicit_failed_end(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests()[0]
    finished = runner.decide(
        request["id"],
        choice="reject",
        comment="Needs changes.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
    )

    assert finished["status"] == "failed"
    assert json.loads(finished["error_json"])["code"] == "DELIVERABLE_REJECTED"


def test_paused_run_records_human_decision_without_dispatching_downstream(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "write a release note"})
    paused = runner.pause(
        waiting["id"],
        expected_version=waiting["version"],
        reason="Wait for the release window.",
    )
    request = runner.pending_human_requests(waiting["id"])[0]

    decided = runner.decide(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
    )

    assert paused["status"] == "paused"
    assert paused["control_mode"] == "pause"
    assert decided["status"] == "paused"
    assert runner.resume(
        decided["id"],
        expected_version=decided["version"],
        reason="Release window is open.",
    )["status"] == "succeeded"


def test_cancelled_waiting_run_rejects_a_late_human_decision(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests(waiting["id"])[0]

    cancelled = runner.cancel(
        waiting["id"],
        expected_version=waiting["version"],
        reason="Release was withdrawn.",
    )

    assert cancelled["status"] == "cancelled"
    assert cancelled["control_mode"] == "cancel"
    cancelled_request = runner.ledger.get_human_request(request["id"])
    assert cancelled_request["status"] == "cancelled"
    with pytest.raises(LedgerConflict, match="not pending"):
        runner.decide(
            request["id"],
            choice="approve",
            comment="Too late.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=cancelled_request["version"],
        )


def test_reconciled_success_validates_output_and_resumes_same_invocation(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    attempt_ids_before = {
        item["id"] for item in runner.ledger.list_attempts(waiting["id"])
    }
    reconciled = runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_succeeded",
        evidence_refs=["evidence://provider/succeeded"],
        reason="The provider returned the durable output.",
        actor="example-reviewer",
        output={"text": "Recovered deliverable.", "artifact_refs": []},
    )

    assert reconciled["status"] == "succeeded"
    assert attempt_ids_before <= {
        item["id"] for item in runner.ledger.list_attempts(waiting["id"])
    }
    assert runner.ledger.get_attempt(unknown["id"])["status"] == "succeeded"
    assert runner.ledger.get_invocation(invocation["id"])["status"] == "succeeded"
    assert runner.ledger.get_run(waiting["id"])["status"] == "waiting"
    assert {
        item["node_id"] for item in runner.ledger.list_invocations(waiting["id"])
    } >= {"produce", "critique", "verify", "review"}


def test_reconciled_failure_fails_the_invocation_without_dispatching_downstream(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    invocation_ids_before = {
        item["id"] for item in runner.ledger.list_invocations(waiting["id"])
    }
    runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_failed",
        evidence_refs=["evidence://provider/failed"],
        reason="The provider confirmed failure.",
        actor="example-reviewer",
    )

    assert runner.ledger.get_invocation(invocation["id"])["status"] == "failed"
    assert runner.ledger.get_run(waiting["id"])["status"] == "failed"
    assert {
        item["id"] for item in runner.ledger.list_invocations(waiting["id"])
    } == invocation_ids_before


def test_reconciled_cancellation_cancels_the_run_without_marking_success(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)

    runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_cancelled",
        evidence_refs=["evidence://provider/cancelled"],
        reason="The provider confirmed the execution was stopped.",
        actor="example-reviewer",
    )

    assert runner.ledger.get_invocation(invocation["id"])["status"] == "cancelled"
    assert runner.ledger.get_run(waiting["id"])["status"] == "cancelled"


def test_reconciliation_cannot_replace_a_human_decision(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "write a release note"})
    invocation = next(
        item
        for item in runner.ledger.list_invocations(waiting["id"])
        if item["node_id"] == "review"
    )
    attempt = runner.ledger.latest_attempt(invocation["id"])
    assert attempt is not None
    unknown = runner.ledger.finish_attempt(attempt["id"], status="unknown")

    with pytest.raises(LedgerConflict, match="human"):
        runner.reconcile_attempt(
            unknown["id"],
            expected_version=unknown["version"],
            conclusion="confirmed_succeeded",
            evidence_refs=["evidence://operator/review"],
            reason="The provider returned a review-shaped result.",
            actor="example-reviewer",
            output={"decision": "approve", "comment": "Approved."},
        )

    assert runner.ledger.get_attempt(unknown["id"])["status"] == "unknown"
    assert runner.pending_human_requests(waiting["id"])[0]["status"] == "pending"


def test_reconciliation_cannot_revive_a_terminal_run(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    terminal = runner.ledger.update_run(
        waiting["id"],
        status="failed",
        error={"code": "TEST_TERMINAL", "message": "Already failed."},
    )

    with pytest.raises(LedgerConflict, match="terminal"):
        runner.reconcile_attempt(
            unknown["id"],
            expected_version=unknown["version"],
            conclusion="confirmed_succeeded",
            evidence_refs=["evidence://provider/succeeded"],
            reason="Late success observation.",
            actor="example-reviewer",
            output={"text": "Recovered deliverable.", "artifact_refs": []},
        )

    assert runner.ledger.get_run(waiting["id"])["version"] == terminal["version"]
    assert runner.ledger.get_run(waiting["id"])["status"] == "failed"
    assert runner.ledger.get_attempt(unknown["id"])["status"] == "unknown"


def test_reconciled_success_after_cancel_finishes_the_run_as_cancelled(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    stopping = runner.cancel(
        waiting["id"],
        expected_version=runner.ledger.get_run(waiting["id"])["version"],
        reason="Stop before the provider result arrives.",
    )

    reconciled = runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_succeeded",
        evidence_refs=["evidence://provider/succeeded"],
        reason="The provider returned a durable result after cancellation.",
        actor="example-reviewer",
        output={"text": "Late result.", "artifact_refs": []},
    )

    assert stopping["status"] == "stopping"
    assert reconciled["status"] == "succeeded"
    assert runner.ledger.get_invocation(invocation["id"])["status"] == "succeeded"
    finished = runner.ledger.get_run(waiting["id"])
    assert finished["status"] == "cancelled"
    assert finished["control_mode"] == "cancel"
    assert {
        item["node_id"] for item in runner.ledger.list_invocations(waiting["id"])
    } == {"produce"}


def test_reconciled_success_respects_a_paused_run_control_intent(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    drive = runner._drive
    runner._drive = lambda run_id, scope_id, node_id: runner.ledger.get_run(run_id)  # type: ignore[method-assign,return-value]
    try:
        waiting = runner.start({"goal": "write a release note"})
    finally:
        runner._drive = drive  # type: ignore[method-assign]
    scope = runner.ledger.list_scopes(waiting["id"])[0]
    invocation = runner.ledger.create_invocation(
        waiting["id"],
        scope["id"],
        "produce",
        {"goal": "write a release note"},
    )
    runner.ledger.finish_invocation(invocation["id"], status="running")
    attempt = runner.ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "write a release note"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )
    runner.ledger.finish_attempt(attempt["id"], status="running")
    paused = runner.pause(
        waiting["id"],
        expected_version=runner.ledger.get_run(waiting["id"])["version"],
        reason="Hold downstream dispatch.",
    )
    unknown = runner.ledger.finish_attempt(attempt["id"], status="unknown")
    reconciled = runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_succeeded",
        evidence_refs=["evidence://provider/succeeded"],
        reason="The provider returned the durable output.",
        actor="example-reviewer",
        output={"text": "Recovered deliverable.", "artifact_refs": []},
    )

    assert paused["control_mode"] == "pause"
    assert reconciled["status"] == "succeeded"
    assert runner.ledger.get_run(waiting["id"])["status"] == "paused"


def test_reconciled_not_started_retries_same_invocation_with_new_dispatch_key(
    tmp_path: Path,
) -> None:
    runner = Runner(
        _write_retrying_content_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    attempts_before = runner.ledger.list_attempts(waiting["id"])

    reconciled = runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_not_started",
        evidence_refs=["evidence://provider/not-started"],
        reason="The provider confirmed that the old submission was never accepted.",
        actor="example-reviewer",
    )

    attempts = runner.ledger.list_attempts(waiting["id"])
    assert reconciled["id"] == unknown["id"]
    invocation_attempts = [
        item for item in attempts if item["invocation_id"] == invocation["id"]
    ]
    assert len(invocation_attempts) == len(attempts_before) + 1
    old_attempt, new_attempt = invocation_attempts[-2:]
    assert old_attempt["id"] == unknown["id"]
    assert old_attempt["status"] == "cancelled"
    assert json.loads(old_attempt["reconciliation_json"])["conclusion"] == (
        "confirmed_not_started"
    )
    assert new_attempt["attempt_no"] == old_attempt["attempt_no"] + 1
    assert new_attempt["invocation_id"] == invocation["id"]
    assert new_attempt["effect_key"] == old_attempt["effect_key"]
    assert new_attempt["dispatch_key"] != old_attempt["dispatch_key"]
    assert new_attempt["status"] == "succeeded"
    assert runner.ledger.get_invocation(invocation["id"])["status"] == "succeeded"
    assert runner.ledger.get_run(waiting["id"])["status"] == "waiting"


def test_reconciled_not_started_does_not_exceed_frozen_max_attempts(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)

    runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_not_started",
        evidence_refs=["evidence://provider/not-started"],
        reason="The provider confirmed that the old submission was never accepted.",
        actor="example-reviewer",
    )

    assert len(runner.ledger.list_attempts(waiting["id"])) == 1
    assert runner.ledger.get_invocation(invocation["id"])["status"] == "failed"
    assert runner.ledger.get_run(waiting["id"])["status"] == "failed"


def test_reconciled_not_started_honors_cancel_control_intent(
    tmp_path: Path,
) -> None:
    runner = Runner(
        _write_retrying_content_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    cancelled = runner.cancel(
        waiting["id"],
        expected_version=runner.ledger.get_run(waiting["id"])["version"],
        reason="Stop the run before any retry.",
    )

    reconciled = runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_not_started",
        evidence_refs=["evidence://provider/not-started"],
        reason="The provider confirmed that the old submission was never accepted.",
        actor="example-reviewer",
    )

    assert cancelled["control_mode"] == "cancel"
    assert reconciled["status"] == "cancelled"
    assert len(runner.ledger.list_attempts(waiting["id"])) == 1
    assert runner.ledger.get_invocation(invocation["id"])["status"] == "cancelled"
    assert runner.ledger.get_run(waiting["id"])["status"] == "cancelled"


def test_reconciled_not_started_preserves_pause_before_retry_dispatch(
    tmp_path: Path,
) -> None:
    runner = Runner(
        _write_retrying_content_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting, invocation, unknown = _start_with_unknown_producer_attempt(runner)
    paused = runner.pause(
        waiting["id"],
        expected_version=runner.ledger.get_run(waiting["id"])["version"],
        reason="Hold the retry until the release window.",
    )

    runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_not_started",
        evidence_refs=["evidence://provider/not-started"],
        reason="The provider confirmed that the old submission was never accepted.",
        actor="example-reviewer",
    )

    attempts = runner.ledger.list_attempts(waiting["id"])
    assert paused["control_mode"] == "pause"
    assert len(attempts) == 2
    assert attempts[-1]["attempt_no"] == 2
    assert attempts[-1]["status"] == "created"
    assert runner.ledger.get_invocation(invocation["id"])["status"] == "running"
    assert runner.ledger.get_run(waiting["id"])["status"] == "paused"

    resumed = runner.resume(
        waiting["id"],
        expected_version=runner.ledger.get_run(waiting["id"])["version"],
        reason="Release window is open.",
    )

    assert resumed["status"] == "waiting"
    assert runner.ledger.get_attempt(attempts[-1]["id"])["status"] == "succeeded"


def test_determined_executor_failure_routes_through_on_error_with_error_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_with_failure(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "example.content-fixture.v1":
            return original_execute(executor_ref, input_value, config)
        assert isinstance(input_value, dict)
        if "error" in input_value:
            error = input_value["error"]
            assert isinstance(error, dict)
            return ExecutionResult(
                output={
                    "handled": True,
                    "errorCode": error["code"],
                }
            )
        raise ExecutorError("provider rejected the request")

    monkeypatch.setattr(runner_module, "execute_builtin", execute_with_failure)
    runner = Runner(
        _write_on_error_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    finished = runner.start({"fail": True})

    assert finished["status"] == "succeeded"
    assert json.loads(finished["output_json"]) == {
        "handled": True,
        "errorCode": "EXECUTOR_FAILED",
    }
    work = next(
        item
        for item in runner.ledger.list_invocations(finished["id"])
        if item["node_id"] == "work"
    )
    handler = next(
        item
        for item in runner.ledger.list_invocations(finished["id"])
        if item["node_id"] == "handle"
    )
    assert work["status"] == "failed"
    assert json.loads(work["output_json"])["error"] == {
        "code": "EXECUTOR_FAILED",
        "message": "provider rejected the request",
        "retryable": False,
        "details": {},
        "evidenceRefs": [],
        "nextActions": [],
    }
    assert json.loads(handler["input_json"])["error"]["code"] == "EXECUTOR_FAILED"
    assert any(
        event["type"] == "error.routed"
        for event in runner.ledger.list_events(finished["id"])
    )


def test_confirmed_failure_routes_after_reconciliation_but_unknown_stays_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_handler(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "example.content-fixture.v1":
            return original_execute(executor_ref, input_value, config)
        assert isinstance(input_value, dict)
        if "error" not in input_value:
            raise ExecutorError("the external provider failed")
        error = input_value["error"]
        assert isinstance(error, dict)
        return ExecutionResult(
            output={"handled": True, "errorCode": error["code"]},
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_handler)
    runner = Runner(
        _write_on_error_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    drive = runner._drive
    runner._drive = lambda run_id, scope_id, node_id: runner.ledger.get_run(run_id)  # type: ignore[method-assign,return-value]
    try:
        blocked = runner.start({"fail": True})
    finally:
        runner._drive = drive  # type: ignore[method-assign]
    scope = runner.ledger.list_scopes(blocked["id"])[0]
    invocation = runner.ledger.create_invocation(
        blocked["id"],
        scope["id"],
        "work",
        {"fail": True},
    )
    runner.ledger.finish_invocation(invocation["id"], status="running")
    attempt = runner.ledger.create_attempt(
        invocation["id"],
        input_value={"fail": True},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )
    runner.ledger.finish_attempt(attempt["id"], status="running")
    unknown = runner.ledger.finish_attempt(attempt["id"], status="unknown")
    runner.ledger.update_run(
        blocked["id"],
        status="running",
        current_node_id="work",
    )

    assert runner.ledger.get_run(blocked["id"])["status"] == "running"
    assert not any(
        item["node_id"] == "handle"
        for item in runner.ledger.list_invocations(blocked["id"])
    )

    reconciled = runner.reconcile_attempt(
        unknown["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_failed",
        evidence_refs=["evidence://provider/failure"],
        reason="The provider confirmed a terminal failure.",
        actor="example-reviewer",
    )

    finished = runner.ledger.get_run(blocked["id"])
    assert reconciled["status"] == "failed"
    assert finished["status"] == "succeeded"
    assert json.loads(finished["output_json"]) == {
        "handled": True,
        "errorCode": "RECONCILED_FAILURE",
    }
    work = runner.ledger.get_invocation(invocation["id"])
    assert work is not None
    assert json.loads(work["output_json"])["error"]["code"] == "RECONCILED_FAILURE"
    assert runner.ledger.get_invocation_for_node(scope["id"], "handle") is not None


def test_rerun_creates_a_new_waiting_run_without_reusing_the_approval(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "write a release note"})
    first_request = runner.pending_human_requests(waiting["id"])[0]
    finished = runner.decide(
        first_request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=first_request["subject_digest"],
        expected_version=first_request["version"],
    )

    rerun = runner.rerun(finished["id"], reason="Run the acceptance flow again.")
    requests = runner.pending_human_requests(rerun["id"])

    assert finished["status"] == "succeeded"
    assert rerun["status"] == "waiting"
    assert rerun["id"] != finished["id"]
    assert rerun["rerun_of"] == finished["id"]
    assert len(requests) == 1
    assert requests[0]["id"] != first_request["id"]


def test_repeat_runs_each_iteration_in_an_independent_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_round(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "example.content-fixture.v1":
            return original_execute(executor_ref, input_value, config)
        assert isinstance(input_value, dict)
        round_number = input_value["round"] + 1
        return ExecutionResult(
            output={
                "round": round_number,
                "completeAfter": input_value["completeAfter"],
                "valid": round_number >= input_value["completeAfter"],
            }
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_round)
    runner = Runner(
        _write_repeat_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    finished = runner.start({"round": 0, "completeAfter": 2})

    assert finished["status"] == "succeeded"
    assert json.loads(finished["output_json"]) == {
        "round": 2,
        "completeAfter": 2,
        "valid": True,
    }
    scopes = runner.ledger.list_scopes(finished["id"])
    assert [json.loads(scope["path_json"]) for scope in scopes] == [
        ["root"],
        ["root", "repair", "1"],
        ["root", "repair", "2"],
    ]
    assert [scope["status"] for scope in scopes] == ["succeeded", "succeeded", "succeeded"]


def test_repeat_fails_when_the_iteration_limit_is_reached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_round(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "example.content-fixture.v1":
            return original_execute(executor_ref, input_value, config)
        assert isinstance(input_value, dict)
        round_number = input_value["round"] + 1
        return ExecutionResult(
            output={
                "round": round_number,
                "completeAfter": input_value["completeAfter"],
                "valid": False,
            }
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_round)
    runner = Runner(
        _write_repeat_package(tmp_path, max_iterations=2),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    failed = runner.start({"round": 0, "completeAfter": 3})

    assert failed["status"] == "failed"
    assert json.loads(failed["error_json"])["code"] == "LOOP_LIMIT_EXCEEDED"
    scopes = runner.ledger.list_scopes(failed["id"])
    assert [json.loads(scope["path_json"]) for scope in scopes] == [
        ["root"],
        ["root", "repair", "1"],
        ["root", "repair", "2"],
    ]
    assert all(scope["status"] == "succeeded" for scope in scopes[1:])


def test_repeat_projection_keeps_each_child_scope_and_its_frozen_nodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_round(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "example.content-fixture.v1":
            return original_execute(executor_ref, input_value, config)
        assert isinstance(input_value, dict)
        round_number = input_value["round"] + 1
        return ExecutionResult(
            output={
                "round": round_number,
                "completeAfter": input_value["completeAfter"],
                "valid": round_number >= input_value["completeAfter"],
            }
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_round)
    runner = Runner(
        _write_repeat_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    finished = runner.start({"round": 0, "completeAfter": 2})

    projection = build_run_projection(runner.ledger, finished["id"])
    child_scopes = [scope for scope in projection["scopes"] if len(scope["path"]) > 1]
    node_ids = {node["id"] for node in projection["nodes"]}

    assert len(child_scopes) == 2
    assert all(f"{scope['id']}:work" in node_ids for scope in child_scopes)
    assert all(f"{scope['id']}:complete" in node_ids for scope in child_scopes)


def test_repeat_creates_a_new_human_request_for_each_iteration(tmp_path: Path) -> None:
    runner = Runner(
        _write_repeat_review_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    first_waiting = runner.start({"goal": "review the release"})
    first_request = runner.pending_human_requests(first_waiting["id"])[0]
    second_waiting = runner.decide(
        first_request["id"],
        choice="reject",
        comment="Needs another pass.",
        actor="example-reviewer",
        subject_digest=first_request["subject_digest"],
        expected_version=first_request["version"],
    )
    second_request = runner.pending_human_requests(second_waiting["id"])[0]
    finished = runner.decide(
        second_request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=second_request["subject_digest"],
        expected_version=second_request["version"],
    )

    assert finished["status"] == "succeeded"
    assert first_request["id"] != second_request["id"]
    assert first_request["scope_id"] != second_request["scope_id"]
    scopes = runner.ledger.list_scopes(finished["id"])
    assert [json.loads(scope["path_json"]) for scope in scopes] == [
        ["root"],
        ["root", "review-loop", "1"],
        ["root", "review-loop", "2"],
    ]


def test_repeat_preflights_child_workflow_executors_before_recording_a_run(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    runner = Runner(
        _write_repeat_package(tmp_path),
        binding_path=ROOT / "examples/bindings/content-remote.yaml",
        database_path=database,
    )

    with pytest.raises(RunError, match="EXECUTOR_UNAVAILABLE.*example.remote-content.v1"):
        runner.start({"round": 0, "completeAfter": 1})

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_content_delivery_passes_two_agent_outputs_to_human_review(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )

    waiting = runner.start({"goal": "write a release note"})

    invocations = {
        invocation["node_id"]: invocation
        for invocation in runner.ledger.list_invocations(waiting["id"])
    }
    assert {"produce", "critique", "verify", "review"} <= set(invocations)
    critique_output = json.loads(invocations["critique"]["output_json"])
    assert critique_output["text"] == "Review of: Deliverable for: write a release note"
    request = runner.pending_human_requests(waiting["id"])[0]
    request_input = json.loads(request["input_json"])
    assert request_input["deliverable"]["text"]
    assert request_input["agentReview"] == critique_output


def test_runner_uses_an_injected_registry_when_compiling_a_binding(tmp_path: Path) -> None:
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        (ROOT / "examples/bindings/content-local.yaml")
        .read_text(encoding="utf-8")
        .replace("example.content-fixture.v1", "test.content-agent.v1"),
        encoding="utf-8",
    )
    local = local_executor_registry()
    registry = ExecutorRegistry(
        [
            ExecutorDescriptor(
                executor_ref="test.content-agent.v1",
                adapter="builtin",
                capabilities=frozenset({"content.produce@1", "content.review@1"}),
                contract_version="multiverse/v0.1",
                executor_version="1.0.0",
                supports_cancel=True,
                supports_idempotency=True,
                supports_recovery_query=True,
                observability_level="structured",
                permission_level="enforced",
                installed=True,
                available=True,
                verified=True,
            ),
            local.resolve("builtin.nonempty-deliverable.v1"),
            local.resolve("builtin.human-review.v1"),
        ]
    )

    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=binding,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )

    assert runner.inspect("run_missing") is None


def test_human_decision_rejects_a_tampered_artifact_in_its_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_with_agent_artifacts(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "builtin.ollama-deliverable.v1":
            return original_execute(executor_ref, input_value, config)
        is_critique = isinstance(input_value, dict) and "deliverable" in input_value
        text = (
            "Critique for the generated deliverable."
            if is_critique
            else "Generated deliverable."
        )
        return ExecutionResult(
            output={"text": text, "artifact_refs": []},
            generated_artifact=GeneratedArtifact(
                name=str(config["artifactName"]),
                media_type="text/markdown",
                content=text.encode("utf-8"),
            ),
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_with_agent_artifacts)
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-ollama.yaml",
        database_path=tmp_path / "runtime.db",
    )

    waiting = runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests(waiting["id"])[0]
    produce = next(
        invocation
        for invocation in runner.ledger.list_invocations(waiting["id"])
        if invocation["node_id"] == "produce"
    )
    artifact_id = json.loads(produce["output_json"])["artifact_refs"][0]
    artifact = runner.ledger.get_artifact(artifact_id)
    assert artifact is not None
    Path(artifact["storage_ref"]).write_text("tampered", encoding="utf-8")

    with pytest.raises(LedgerConflict, match="artifact digest mismatch"):
        runner.decide(
            request["id"],
            choice="approve",
            comment="Approved.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
        )

    assert runner.ledger.get_human_request(request["id"])["status"] == "pending"


def test_runner_blocks_critic_dispatch_when_producer_artifact_is_tampered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_with_agent_artifact(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "builtin.ollama-deliverable.v1":
            return original_execute(executor_ref, input_value, config)
        return ExecutionResult(
            output={"text": "Generated deliverable.", "artifact_refs": []},
            generated_artifact=GeneratedArtifact(
                name=str(config["artifactName"]),
                media_type="text/markdown",
                content=b"Generated deliverable.",
            ),
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_with_agent_artifact)
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-ollama.yaml",
        database_path=tmp_path / "runtime.db",
    )
    original_validate = runner.ledger.validate_artifact_refs
    producer_artifact_validated = False

    def tamper_before_critic_dispatch(run_id: str, artifact_refs: list[str]) -> None:
        nonlocal producer_artifact_validated
        if artifact_refs and producer_artifact_validated:
            artifact = runner.ledger.get_artifact(artifact_refs[0])
            assert artifact is not None
            Path(artifact["storage_ref"]).write_text("tampered", encoding="utf-8")
        original_validate(run_id, artifact_refs)
        if artifact_refs:
            producer_artifact_validated = True

    monkeypatch.setattr(
        runner.ledger,
        "validate_artifact_refs",
        tamper_before_critic_dispatch,
    )

    failed = runner.start({"goal": "write a release note"})

    assert failed["status"] == "failed"
    assert json.loads(failed["error_json"])["code"] == "INPUT_ARTIFACT_INVALID"
    invocations = {
        invocation["node_id"]: invocation
        for invocation in runner.ledger.list_invocations(failed["id"])
    }
    assert invocations["produce"]["status"] == "succeeded"
    assert invocations["critique"]["status"] == "failed"


def test_human_decision_accepts_persisted_two_agent_artifact_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_with_agent_artifacts(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "builtin.ollama-deliverable.v1":
            return original_execute(executor_ref, input_value, config)
        is_critique = isinstance(input_value, dict) and "deliverable" in input_value
        text = "Critique." if is_critique else "Deliverable."
        return ExecutionResult(
            output={"text": text, "artifact_refs": []},
            generated_artifact=GeneratedArtifact(
                name=str(config["artifactName"]),
                media_type="text/markdown",
                content=text.encode("utf-8"),
            ),
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_with_agent_artifacts)
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-ollama.yaml",
        database_path=tmp_path / "runtime.db",
    )

    waiting = runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests(waiting["id"])[0]

    finished = runner.decide(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
    )

    assert finished["status"] == "succeeded"


def test_runner_registers_a_generated_agent_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_with_generated_artifact(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "builtin.ollama-deliverable.v1":
            return original_execute(executor_ref, input_value, config)
        return ExecutionResult(
            output={"text": "Generated by a managed agent.", "artifact_refs": []},
            generated_artifact=GeneratedArtifact(
                name="agent-deliverable.md",
                media_type="text/markdown",
                content=b"# Agent deliverable\n",
            ),
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_with_generated_artifact)
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-ollama.yaml",
        database_path=tmp_path / "runtime.db",
    )

    waiting = runner.start({"goal": "write a release note"})

    produce = next(
        invocation
        for invocation in runner.ledger.list_invocations(waiting["id"])
        if invocation["node_id"] == "produce"
    )
    output = json.loads(produce["output_json"])
    assert len(output["artifact_refs"]) == 1
    artifact = runner.ledger.get_artifact(output["artifact_refs"][0])
    assert artifact is not None
    assert artifact["invocation_id"] == produce["id"]
    assert Path(artifact["storage_ref"]).read_bytes() == b"# Agent deliverable\n"


def test_runner_fails_an_invalid_generated_artifact_without_registering_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from multiverse_workflow.runtime import runner as runner_module

    original_execute = runner_module.execute_builtin

    def execute_with_invalid_artifact(
        executor_ref: str,
        input_value: object,
        config: dict[str, object],
    ) -> ExecutionResult:
        if executor_ref != "builtin.ollama-deliverable.v1":
            return original_execute(executor_ref, input_value, config)
        return ExecutionResult(
            output={
                "text": "Generated by a managed agent.",
                "artifact_refs": [],
                "unrecognized": True,
            },
            generated_artifact=GeneratedArtifact(
                name="agent-deliverable.md",
                media_type="text/markdown",
                content=b"# Agent deliverable\n",
            ),
        )

    monkeypatch.setattr(runner_module, "execute_builtin", execute_with_invalid_artifact)
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-ollama.yaml",
        database_path=tmp_path / "runtime.db",
    )

    failed = runner.start({"goal": "write a release note"})

    assert failed["status"] == "failed"
    assert json.loads(failed["error_json"])["code"] == "EXECUTOR_OUTPUT_INVALID"
    produce = next(
        invocation
        for invocation in runner.ledger.list_invocations(failed["id"])
        if invocation["node_id"] == "produce"
    )
    assert produce["status"] == "failed"
    assert runner.ledger.latest_attempt(produce["id"])["status"] == "failed"
    assert list((tmp_path / "artifacts").iterdir()) == []


def test_repeated_decision_command_does_not_replay_downstream_nodes(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests()[0]

    first = runner.decide(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
        idempotency_key="decision-1",
    )
    event_count = len(runner.ledger.list_events(first["id"]))
    repeated = runner.decide(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
        idempotency_key="decision-1",
    )

    assert repeated["id"] == first["id"]
    assert repeated["status"] == "succeeded"
    assert len(runner.ledger.list_events(first["id"])) == event_count


def test_repeated_decision_resumes_a_persisted_decision_after_process_exit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.db"
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=database,
    )
    waiting = runner.start({"goal": "write a release note"})
    request = runner.pending_human_requests(waiting["id"])[0]
    runner.ledger.decide_human_request(
        request["id"],
        choice="approve",
        comment="Approved.",
        expected_version=request["version"],
        subject_digest=request["subject_digest"],
        actor="example-reviewer",
        idempotency_key="decision-after-exit",
    )

    resumed = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=database,
    )
    finished = resumed.decide(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
        idempotency_key="decision-after-exit",
    )

    assert finished["status"] == "succeeded"
    invocation = resumed.ledger.get_invocation(request["invocation_id"])
    assert invocation is not None
    assert invocation["status"] == "succeeded"


def test_unavailable_adapter_is_rejected_before_a_run_is_recorded(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-remote.yaml",
        database_path=database,
    )

    with pytest.raises(RunError, match="EXECUTOR_UNAVAILABLE.*example.remote-content.v1"):
        runner.start({"goal": "do not dispatch remote work"})

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_resume_blocks_a_binding_digest_that_changed_after_run_start(tmp_path: Path) -> None:
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        (ROOT / "examples/bindings/content-local.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    database = tmp_path / "runtime.db"
    first = Runner(
        ROOT / "presets/content-delivery",
        binding_path=binding,
        database_path=database,
    )
    waiting = first.start({"goal": "prepare a release"})
    request = first.pending_human_requests(waiting["id"])[0]

    binding.write_text(
        binding.read_text(encoding="utf-8").replace(
            "version: 0.1.0",
            "version: 0.1.1",
        ),
        encoding="utf-8",
    )
    resumed = Runner(
        ROOT / "presets/content-delivery",
        binding_path=binding,
        database_path=database,
    )

    with pytest.raises(RunError, match="runtime definition drift.*binding digest"):
        resumed.decide(
            request["id"],
            choice="approve",
            comment="Approved.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
        )


def _write_manual_input_package(root: Path) -> tuple[Path, Path]:
    package = root / "manual-input"
    shutil.copytree(ROOT / "presets/content-delivery", package)
    (package / "schemas/review-input.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["goal"],
                "properties": {"goal": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    (package / "schemas/review-output.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["artifact_refs", "change_summary"],
                "properties": {
                    "artifact_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "change_summary": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    workflow = (package / "workflows/delivery.yaml").read_text(encoding="utf-8")
    workflow = workflow.replace("requestType: review", "requestType: input")
    workflow = workflow.replace("Human review", "Manual delivery")
    workflow = workflow.replace("human.review@1", "human.input@1")
    workflow = workflow.replace("      next: review-route", "      next: complete")
    start = workflow.index("    review-route:")
    end = workflow.index("    complete:", start)
    workflow = workflow[:start] + workflow[end:]
    start = workflow.index("    rejected:")
    workflow = workflow[:start]
    workflow = workflow.replace(
        """      input:
        object:
          deliverable: {ref: "nodes.produce.output#"}
          agentReview: {ref: "nodes.critique.output#"}
          verification: {ref: "nodes.verify.output#"}
""",
        """      input:
        ref: input#
""",
    )
    (package / "workflows/delivery.yaml").write_text(workflow, encoding="utf-8")
    binding = root / "manual-input-binding.yaml"
    binding.write_text(
        (ROOT / "examples/bindings/content-local.yaml")
        .read_text(encoding="utf-8")
        .replace("builtin.human-review.v1", "builtin.human-input.v1")
        .replace("human.review@1", "human.input@1")
        .replace("requestType: review", "requestType: input")
        .replace("choices: [approve, reject]", "choices: []"),
        encoding="utf-8",
    )
    return package, binding


def _write_retrying_content_package(root: Path) -> Path:
    package = root / "retrying-content"
    shutil.copytree(ROOT / "presets/content-delivery", package)
    workflow_path = package / "workflows/delivery.yaml"
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow = workflow.replace(
        """      retry:
        maxAttempts: 1
      next: critique
""",
        """      retry:
        maxAttempts: 2
      next: critique
""",
        1,
    )
    workflow_path.write_text(workflow, encoding="utf-8")
    return package


def _write_on_error_package(root: Path) -> Path:
    package = root / "on-error-package"
    shutil.copytree(ROOT / "presets/content-delivery", package)
    schemas = package / "schemas"
    (schemas / "request.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["fail"],
                "properties": {"fail": {"type": "boolean"}},
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    (schemas / "work-output.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": True,
            }
        ),
        encoding="utf-8",
    )
    (schemas / "handler-input.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": True,
            }
        ),
        encoding="utf-8",
    )
    (schemas / "final-output.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["handled", "errorCode"],
                "properties": {
                    "handled": {"type": "boolean"},
                    "errorCode": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )
    (package / "manifest.yaml").write_text(
        """\
apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: on-error-package
  version: 0.1.0
spec:
  workflows:
    main: workflows/main.yaml
  entrypoints: [main]
  requiredFeatures: [core.call]
""",
        encoding="utf-8",
    )
    (package / "workflows/main.yaml").write_text(
        """\
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: main
  version: 0.1.0
spec:
  inputSchema: schemas/request.json
  outputSchema: schemas/final-output.json
  entry: work
  nodes:
    work:
      type: call
      slot: producer
      inputSchema: schemas/request.json
      outputSchema: schemas/work-output.json
      input: {ref: input#}
      requires:
        capabilities: [content.produce@1]
      effects:
        class: none
        actions: []
      onError: handle
      next: handle
    handle:
      type: call
      slot: producer
      inputSchema: schemas/handler-input.json
      outputSchema: schemas/final-output.json
      input: {ref: nodes.work.output#}
      requires:
        capabilities: [content.produce@1]
      effects:
        class: none
        actions: []
      next: complete
    complete:
      type: end
      outcome: succeeded
      output: {ref: nodes.handle.output#}
""",
        encoding="utf-8",
    )
    return package


def _write_repeat_package(root: Path, *, max_iterations: int = 3) -> Path:
    package = root / "repeat-package"
    schemas = package / "schemas"
    workflows = package / "workflows"
    schemas.mkdir(parents=True)
    workflows.mkdir()
    round_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["round", "completeAfter"],
        "properties": {
            "round": {"type": "integer", "minimum": 0},
            "completeAfter": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    }
    round_output_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["round", "completeAfter", "valid"],
        "properties": {
            "round": {"type": "integer", "minimum": 1},
            "completeAfter": {"type": "integer", "minimum": 1},
            "valid": {"type": "boolean"},
        },
        "additionalProperties": False,
    }
    (schemas / "round-input.json").write_text(
        json.dumps(round_schema),
        encoding="utf-8",
    )
    (schemas / "round-output.json").write_text(
        json.dumps(round_output_schema),
        encoding="utf-8",
    )
    (package / "manifest.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: repeat-package
  version: 0.1.0
spec:
  workflows:
    delivery: workflows/delivery.yaml
    repair-round: workflows/repair-round.yaml
  entrypoints: [delivery]
  requiredFeatures: [core.call, core.repeat]
""",
        encoding="utf-8",
    )
    (workflows / "delivery.yaml").write_text(
        f"""apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: delivery
  version: 0.1.0
spec:
  inputSchema: schemas/round-input.json
  outputSchema: schemas/round-output.json
  entry: repair
  nodes:
    repair:
      type: repeat
      workflow: repair-round
      input:
        ref: input#
      until:
        op: eq
        left: {{ref: "iteration.output#/valid"}}
        right: {{literal: true}}
      feedback:
        object:
          round: {{ref: "iteration.output#/round"}}
          completeAfter: {{ref: "iteration.output#/completeAfter"}}
      maxIterations: {max_iterations}
      next: complete
    complete:
      type: end
      outcome: succeeded
      output:
        ref: nodes.repair.output#
""",
        encoding="utf-8",
    )
    (workflows / "repair-round.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: repair-round
  version: 0.1.0
spec:
  inputSchema: schemas/round-input.json
  outputSchema: schemas/round-output.json
  entry: work
  nodes:
    work:
      type: call
      slot: producer
      inputSchema: schemas/round-input.json
      outputSchema: schemas/round-output.json
      input:
        ref: input#
      requires:
        capabilities: [content.produce@1]
      effects:
        class: none
        actions: []
      next: complete
    complete:
      type: end
      outcome: succeeded
      output:
        ref: nodes.work.output#
""",
        encoding="utf-8",
    )
    return package


def _write_repeat_review_package(root: Path) -> Path:
    package = root / "repeat-review-package"
    schemas = package / "schemas"
    workflows = package / "workflows"
    schemas.mkdir(parents=True)
    workflows.mkdir()
    request_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["goal"],
        "properties": {"goal": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }
    review_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["decision", "comment"],
        "properties": {
            "decision": {"type": "string", "enum": ["approve", "reject"]},
            "comment": {"type": "string"},
        },
        "additionalProperties": False,
    }
    (schemas / "request.json").write_text(json.dumps(request_schema), encoding="utf-8")
    (schemas / "review.json").write_text(json.dumps(review_schema), encoding="utf-8")
    (package / "manifest.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: repeat-review-package
  version: 0.1.0
spec:
  workflows:
    delivery: workflows/delivery.yaml
    review-round: workflows/review-round.yaml
  entrypoints: [delivery]
  requiredFeatures: [core.call, core.human, core.repeat]
""",
        encoding="utf-8",
    )
    (workflows / "delivery.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: delivery
  version: 0.1.0
spec:
  inputSchema: schemas/request.json
  outputSchema: schemas/review.json
  entry: review-loop
  nodes:
    review-loop:
      type: repeat
      workflow: review-round
      input:
        ref: input#
      until:
        op: eq
        left: {ref: "iteration.output#/decision"}
        right: {literal: approve}
      feedback:
        ref: input#
      maxIterations: 2
      next: complete
    complete:
      type: end
      outcome: succeeded
      output:
        ref: nodes.review-loop.output#
""",
        encoding="utf-8",
    )
    (workflows / "review-round.yaml").write_text(
        """apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: review-round
  version: 0.1.0
spec:
  inputSchema: schemas/request.json
  outputSchema: schemas/review.json
  entry: review
  nodes:
    review:
      type: call
      slot: reviewer
      inputSchema: schemas/request.json
      outputSchema: schemas/review.json
      input:
        ref: input#
      requires:
        capabilities: [human.review@1]
      effects:
        class: none
        actions: []
      next: complete
    complete:
      type: end
      outcome: succeeded
      output:
        ref: nodes.review.output#
""",
        encoding="utf-8",
    )
    return package


def test_input_human_request_accepts_a_structured_artifact_result(tmp_path: Path) -> None:
    package, binding = _write_manual_input_package(tmp_path)
    runner = Runner(package, binding_path=binding, database_path=tmp_path / "runtime.db")
    waiting = runner.start({"goal": "prepare a release"})
    request = runner.pending_human_requests()[0]
    artifact_source = tmp_path / "release.md"
    artifact_source.write_text("# Release", encoding="utf-8")
    artifact = runner.ledger.register_artifact(
        run_id=waiting["id"],
        source_path=artifact_source,
        name="release.md",
        media_type="text/markdown",
    )

    finished = runner.decide(
        request["id"],
        decision={
            "artifact_refs": [artifact["id"]],
            "change_summary": "Prepared the release document.",
        },
        comment="Submitted by editor.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
    )

    assert finished["status"] == "succeeded"
    output = json.loads(finished["output_json"])
    assert output["review"]["artifact_refs"] == [artifact["id"]]


def test_input_human_request_rejects_an_unknown_artifact(tmp_path: Path) -> None:
    package, binding = _write_manual_input_package(tmp_path)
    runner = Runner(package, binding_path=binding, database_path=tmp_path / "runtime.db")
    runner.start({"goal": "prepare a release"})
    request = runner.pending_human_requests()[0]

    with pytest.raises(LedgerConflict, match="artifact"):
        runner.decide(
            request["id"],
            decision={"artifact_refs": ["artifact_missing"], "change_summary": "done"},
            comment="Submitted by editor.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
        )

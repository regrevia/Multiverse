import json
from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict


def test_ledger_persists_run_scope_invocation_attempt_and_events(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")

    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest="sha256:binding",
        plan={"workflowId": "delivery"},
        input_value={"goal": "write"},
        deadline_at="2026-09-20T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"])
    invocation = ledger.create_invocation(
        run["id"],
        scope["id"],
        "produce",
        {"goal": "write"},
        "sha256:input",
    )
    attempt = ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "write"},
        dispatch_key="dispatch-1",
        effect_key="effect-1",
    )
    ledger.finish_attempt(
        attempt["id"],
        status="succeeded",
        output={"text": "done"},
    )
    ledger.finish_invocation(invocation["id"], status="succeeded", output={"text": "done"})
    ledger.update_run(run["id"], status="waiting", current_node_id="review")

    loaded = ledger.get_run(run["id"])
    assert loaded is not None
    assert loaded["status"] == "waiting"
    assert loaded["current_node_id"] == "review"
    assert loaded["version"] == 2
    assert ledger.list_events(run["id"])[-1]["type"] == "run.updated"
    assert ledger.get_attempt(attempt["id"])["status"] == "succeeded"
    assert json.loads(ledger.get_attempt(attempt["id"])["output_json"]) == {"text": "done"}


def test_human_request_decision_is_versioned_and_idempotent(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest="sha256:binding",
        plan={},
        input_value={},
        deadline_at="2026-09-20T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"])
    invocation = ledger.create_invocation(run["id"], scope["id"], "review", {}, "sha256:input")
    request = ledger.create_human_request(
        run_id=run["id"],
        scope_id=scope["id"],
        invocation_id=invocation["id"],
        request_type="review",
        title="Review deliverable",
        instructions="Choose approve or reject.",
        input_value={"text": "done"},
        subject_digest="sha256:subject",
        choices=["approve", "reject"],
        decision_schema={"type": "object"},
        authorized_subjects=["example-reviewer"],
        expires_at="2099-01-01T00:00:00Z",
    )

    decided = ledger.decide_human_request(
        request["id"],
        choice="approve",
        comment="Looks good.",
        expected_version=1,
        subject_digest="sha256:subject",
        actor="example-reviewer",
        idempotency_key="decision-1",
    )
    repeated = ledger.decide_human_request(
        request["id"],
        choice="approve",
        comment="Looks good.",
        expected_version=1,
        subject_digest="sha256:subject",
        actor="example-reviewer",
        idempotency_key="decision-1",
    )

    assert decided["status"] == "decided"
    assert decided["version"] == 2
    assert repeated["id"] == decided["id"]
    assert ledger.list_events(run["id"])[-1]["type"] == "human.decided"

    with pytest.raises(LedgerConflict, match="version"):
        ledger.decide_human_request(
            request["id"],
            choice="reject",
            comment="No.",
            expected_version=1,
            subject_digest="sha256:subject",
            actor="example-reviewer",
            idempotency_key="decision-2",
        )


def test_ledger_rejects_an_unauthorized_human_subject(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2026-09-20T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"])
    invocation = ledger.create_invocation(run["id"], scope["id"], "review", {}, "sha256:input")
    request = ledger.create_human_request(
        run_id=run["id"],
        scope_id=scope["id"],
        invocation_id=invocation["id"],
        request_type="review",
        title="Review",
        instructions="Review.",
        input_value={},
        subject_digest="sha256:subject",
        choices=["approve"],
        decision_schema={"type": "object"},
        authorized_subjects=["reviewer"],
        expires_at="2026-09-20T00:00:00Z",
    )

    with pytest.raises(LedgerConflict, match="authorized"):
        ledger.decide_human_request(
            request["id"],
            choice="approve",
            comment="",
            expected_version=1,
            subject_digest="sha256:subject",
            actor="unknown",
            idempotency_key="decision-1",
        )


def test_ledger_registers_an_immutable_local_artifact(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2026-09-20T00:00:00Z",
    )
    source = tmp_path / "deliverable.txt"
    source.write_text("approved content", encoding="utf-8")

    artifact = ledger.register_artifact(
        run_id=run["id"],
        source_path=source,
        name="deliverable.txt",
        media_type="text/plain",
    )

    assert artifact["status"] == "ready"
    assert artifact["size_bytes"] == len(b"approved content")
    assert artifact["digest"].startswith("sha256:")
    stored = Path(artifact["storage_ref"])
    assert stored.is_file()
    assert stored.read_text(encoding="utf-8") == "approved content"
    assert ledger.get_artifact(artifact["id"])["id"] == artifact["id"]

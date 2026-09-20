import json
import sqlite3
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
    scope = ledger.create_scope(
        run["id"],
        "delivery",
        path=["root"],
        input_value={"goal": "write"},
    )
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
    assert json.loads(ledger.get_scope(scope["id"])["input_json"]) == {"goal": "write"}


def test_ledger_reconciles_unknown_attempt_once_with_evidence(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2099-01-01T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"])
    invocation = ledger.create_invocation(run["id"], scope["id"], "produce", {})
    attempt = ledger.create_attempt(
        invocation["id"],
        input_value={},
        dispatch_key="dispatch-unknown",
        effect_key="effect-unknown",
    )
    unknown = ledger.finish_attempt(attempt["id"], status="unknown")

    reconciled = ledger.reconcile_attempt(
        attempt["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_failed",
        evidence_refs=["evidence://operator/123"],
        reason="Provider confirmed a terminal failure.",
        actor="example-reviewer",
    )

    assert reconciled["status"] == "failed"
    assert reconciled["version"] == unknown["version"] + 1
    assert json.loads(reconciled["reconciliation_json"]) == {
        "conclusion": "confirmed_failed",
        "evidenceRefs": ["evidence://operator/123"],
        "reason": "Provider confirmed a terminal failure.",
        "actor": "example-reviewer",
    }
    with pytest.raises(LedgerConflict, match="version"):
        ledger.reconcile_attempt(
            attempt["id"],
            expected_version=unknown["version"],
            conclusion="confirmed_cancelled",
            evidence_refs=["evidence://operator/456"],
            reason="Late duplicate.",
            actor="example-reviewer",
        )


def test_unknown_attempt_enters_reconciling_and_blocks_the_run(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2099-01-01T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"])
    invocation = ledger.create_invocation(run["id"], scope["id"], "produce", {})
    attempt = ledger.create_attempt(
        invocation["id"],
        input_value={},
        dispatch_key="dispatch-blocked",
        effect_key="effect-blocked",
    )

    unknown = ledger.finish_attempt(attempt["id"], status="unknown")

    assert unknown["status"] == "unknown"
    assert ledger.get_invocation(invocation["id"])["status"] == "reconciling"
    assert ledger.get_run(run["id"])["status"] == "blocked"


def test_attempt_terminal_state_cannot_be_overwritten_by_late_observation(
    tmp_path: Path,
) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2099-01-01T00:00:00Z",
    )
    scope = ledger.create_scope(run["id"], "delivery", path=["root"])
    invocation = ledger.create_invocation(run["id"], scope["id"], "produce", {})
    attempt = ledger.create_attempt(
        invocation["id"],
        input_value={},
        dispatch_key="dispatch-terminal",
        effect_key="effect-terminal",
    )
    finished = ledger.finish_attempt(attempt["id"], status="succeeded", output={"ok": True})

    with pytest.raises(LedgerConflict, match="terminal"):
        ledger.finish_attempt(attempt["id"], status="failed")

    assert ledger.get_attempt(attempt["id"])["version"] == finished["version"]
    assert ledger.get_attempt(attempt["id"])["status"] == "succeeded"


def test_ledger_persists_child_scope_terminal_output(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={"round": 0},
        deadline_at="2099-01-01T00:00:00Z",
    )
    parent = ledger.create_scope(
        run["id"],
        "delivery",
        path=["root"],
        input_value={"round": 0},
    )
    invocation = ledger.create_invocation(
        run["id"],
        parent["id"],
        "repair",
        {"round": 0},
    )
    child = ledger.create_scope(
        run["id"],
        "repair-round",
        path=["root", "repair", "1"],
        input_value={"round": 0},
        parent_scope_id=parent["id"],
        parent_invocation_id=invocation["id"],
    )

    finished = ledger.finish_scope(
        child["id"],
        status="succeeded",
        output={"round": 1, "valid": True},
    )

    assert finished["status"] == "succeeded"
    assert json.loads(finished["output_json"]) == {"round": 1, "valid": True}
    assert ledger.list_child_scopes(invocation["id"])[0]["id"] == child["id"]


def test_ledger_migrates_legacy_scope_columns(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE scopes (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                parent_scope_id TEXT,
                parent_invocation_id TEXT,
                workflow_id TEXT NOT NULL,
                path_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE human_decisions (
                id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                request_version INTEGER NOT NULL,
                choice TEXT NOT NULL,
                comment TEXT NOT NULL,
                actor TEXT NOT NULL,
                subject_digest TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO scopes (
                id, run_id, parent_scope_id, parent_invocation_id,
                workflow_id, path_json, status, created_at
            ) VALUES (
                'scope_legacy', 'run_legacy', NULL, NULL, 'delivery',
                '["root"]', 'active', '2026-09-20T00:00:00Z'
            )
            """
        )

    ledger = Ledger(database)
    migrated = ledger.get_scope("scope_legacy")

    assert migrated is not None
    assert migrated["input_json"] is None
    assert migrated["output_json"] is None
    assert migrated["error_json"] is None


def test_ledger_migrates_legacy_run_rerun_columns(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                package_digest TEXT NOT NULL,
                binding_digest TEXT,
                plan_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                control_mode TEXT NOT NULL,
                deadline_at TEXT NOT NULL,
                version INTEGER NOT NULL,
                current_node_id TEXT,
                output_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    ledger = Ledger(database)
    columns = {
        row["name"]
        for row in ledger._connection.execute("PRAGMA table_info(runs)").fetchall()
    }
    source = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2099-01-01T00:00:00Z",
    )
    rerun = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2099-01-01T00:00:00Z",
        rerun_of=source["id"],
        rerun_reason="Repeat acceptance.",
    )

    assert {"rerun_of", "rerun_reason"} <= columns
    assert rerun["rerun_of"] == source["id"]
    assert rerun["rerun_reason"] == "Repeat acceptance."


def test_ledger_migrates_legacy_command_scope_and_rebuilds_idempotency_index(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-commands.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE commands (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL,
                operation TEXT NOT NULL,
                namespace TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                status TEXT NOT NULL,
                resource_version INTEGER,
                error_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO commands (
                id, idempotency_key, fingerprint, operation, namespace,
                resource_id, status, resource_version, error_json,
                created_at, updated_at
            ) VALUES (
                'cmd_legacy', 'shared-key', 'fingerprint', 'run.create', 'local',
                'run_legacy', 'completed', 2, NULL,
                '2026-09-20T00:00:00Z', '2026-09-20T00:00:00Z'
            );
            """
        )

    ledger = Ledger(database)
    migrated = ledger.get_command("cmd_legacy")
    assert migrated is not None
    assert migrated["subject"] == "local-user"

    ledger.create_command(
        command_id="cmd_same-key-different-scope",
        idempotency_key="shared-key",
        fingerprint="other-fingerprint",
        operation="run.create",
        namespace="local",
        resource_id="run_other",
        subject="another-user",
    )
    ledger.create_command(
        command_id="cmd_same-key-different-operation",
        idempotency_key="shared-key",
        fingerprint="other-operation",
        operation="run.pause",
        namespace="local",
        resource_id="run_legacy",
        subject="local-user",
    )

    local_commands = ledger.list_commands_by_key(
        "shared-key",
        namespace="local",
        subject="local-user",
    )
    assert {command["operation"] for command in local_commands} == {
        "run.create",
        "run.pause",
    }


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
    intent = ledger.get_human_progress_intent(request["id"])
    assert intent is not None
    assert intent["status"] == "pending"
    assert intent["decision_id"] == ledger.get_human_decision(request["id"])["id"]
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


def test_waits_are_claimable_once_and_complete_by_semantic_key(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "runtime.db")
    run = ledger.create_run(
        namespace="local",
        workflow_id="delivery",
        package_digest="sha256:package",
        binding_digest=None,
        plan={},
        input_value={},
        deadline_at="2099-01-01T00:00:00Z",
    )

    wait = ledger.create_wait(
        namespace="local",
        wait_key="retry:run-1:attempt-1",
        kind="retry",
        run_id=run["id"],
        not_before="2020-01-01T00:00:00Z",
        payload={"attemptId": "attempt-1"},
    )

    assert ledger.list_due_waits(
        now="2020-01-01T00:00:01Z",
    )[0]["id"] == wait["id"]
    claimed = ledger.claim_wait(
        wait["id"],
        worker_id="worker-1",
        now="2020-01-01T00:00:02Z",
    )
    assert claimed is not None
    assert claimed["status"] == "claimed"
    assert ledger.claim_wait(
        wait["id"],
        worker_id="worker-2",
        now="2020-01-01T00:00:03Z",
    ) is None

    completed = ledger.complete_wait(wait["id"])
    assert completed["status"] == "completed"
    assert ledger.get_wait_by_key("local", "retry:run-1:attempt-1")["status"] == (
        "completed"
    )
    assert ledger.list_due_waits(now="2099-01-01T00:00:00Z") == []


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

from pathlib import Path

from multiverse_workflow.runtime.projection import build_run_projection
from multiverse_workflow.runtime.runner import Runner

ROOT = Path(__file__).parents[2]


def test_projection_exposes_frozen_graph_and_waiting_human_request(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "ship the release"})

    projection = build_run_projection(runner.ledger, waiting["id"])
    by_node = {node["nodeId"]: node for node in projection["nodes"]}

    assert projection["protocolVersion"] == "multiverse/v0.1"
    assert projection["run"]["id"] == waiting["id"]
    assert projection["run"]["status"] == "waiting"
    assert projection["scopes"][0]["path"] == ["root"]
    assert by_node["produce"]["status"] == "succeeded"
    assert by_node["produce"]["invocation"]["status"] == "succeeded"
    assert by_node["produce"]["latestAttempt"]["attemptNo"] == 1
    assert by_node["review"]["status"] == "waiting"
    assert by_node["review"]["invocation"]["status"] == "waiting"
    assert projection["humanRequests"][0]["status"] == "pending"
    assert projection["events"][-1]["type"] == "run.updated"


def test_projection_exposes_attempt_reconciliation_audit_facts(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "ship the release"})
    invocation = next(
        item
        for item in runner.ledger.list_invocations(waiting["id"])
        if item["node_id"] == "review"
    )
    attempt = runner.ledger.latest_attempt(invocation["id"])
    assert attempt is not None
    unknown = runner.ledger.finish_attempt(attempt["id"], status="unknown")
    runner.ledger.reconcile_attempt(
        attempt["id"],
        expected_version=unknown["version"],
        conclusion="confirmed_failed",
        evidence_refs=["evidence://provider/failed"],
        reason="Provider confirmed failure.",
        actor="example-reviewer",
    )

    projection = build_run_projection(runner.ledger, waiting["id"])
    summary = next(
        node["latestAttempt"]
        for node in projection["nodes"]
        if node["nodeId"] == "review"
    )

    assert summary["version"] == unknown["version"] + 1
    assert summary["status"] == "failed"
    assert summary["reconciliation"] == {
        "conclusion": "confirmed_failed",
        "evidenceRefs": ["evidence://provider/failed"],
        "reason": "Provider confirmed failure.",
        "actor": "example-reviewer",
    }


def test_projection_preserves_cancelled_invocation_status(tmp_path: Path) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "ship the release"})
    invocation = next(
        item
        for item in runner.ledger.list_invocations(waiting["id"])
        if item["node_id"] == "review"
    )
    runner.ledger.finish_invocation(
        invocation["id"],
        status="cancelled",
        error={"code": "TEST_CANCELLED", "message": "Stopped."},
    )

    projection = build_run_projection(runner.ledger, waiting["id"])
    node = next(item for item in projection["nodes"] if item["nodeId"] == "review")

    assert node["status"] == "cancelled"

from pathlib import Path
from types import SimpleNamespace

from multiverse_workflow.runtime.projection import (
    _execution_summary,
    _scope_data_dependencies,
    _waiting_reason,
    build_run_projection,
)
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
    assert by_node["produce"]["dataSources"] == ["工作流输入"]
    assert "Agent review" in by_node["produce"]["dataTargets"]
    assert "Produce deliverable" in by_node["critique"]["dataSources"]
    assert projection["humanRequests"][0]["status"] == "pending"
    assert projection["events"][-1]["type"] == "run.updated"


def test_data_dependency_projection_covers_call_switch_parallel_and_end_expressions() -> None:
    sources, targets = _scope_data_dependencies(
        {
            "start": {
                "type": "call",
                "title": "开始",
                "input": {"ref": "input#/goal"},
            },
            "branch": {
                "type": "switch",
                "title": "分支",
                "cases": [{"when": {"left": {"ref": "nodes.start.output#/ok"}}}],
            },
            "parallel": {
                "type": "parallel",
                "title": "并行",
                "branches": {
                    "a": {"input": {"ref": "nodes.start.output#/a"}},
                    "b": {"input": {"ref": "nodes.start.output#/b"}},
                },
            },
            "finish": {
                "type": "end",
                "title": "完成",
                "output": {"ref": "nodes.parallel.output#"},
            },
        }
    )

    assert sources == {
        "start": ["工作流输入"],
        "branch": ["开始"],
        "parallel": ["开始"],
        "finish": ["并行"],
    }
    assert targets["start"] == ["分支", "并行"]
    assert targets["parallel"] == ["完成"]


def test_projection_separates_structural_type_from_waiting_participant(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "ship the release"})
    original_list_invocations = runner.ledger.list_invocations

    def list_invocations_with_waiting_call(run_id: str) -> list[dict]:
        invocations = original_list_invocations(run_id)
        return [
            {**invocation, "status": "waiting"}
            if invocation["node_id"] == "produce"
            else invocation
            for invocation in invocations
        ]

    monkeypatch.setattr(runner.ledger, "list_invocations", list_invocations_with_waiting_call)
    projection = build_run_projection(
        runner.ledger,
        waiting["id"],
        binding=runner._binding,
    )
    node = next(item for item in projection["nodes"] if item["nodeId"] == "produce")

    assert node["type"] == "call"
    assert node["execution"] == {
        "participantType": "program",
        "adapter": "builtin",
        "executorRef": "example.content-fixture.v1",
        "location": "runtime",
        "target": "Multiverse Runtime",
        "model": None,
        "workspace": None,
    }
    assert node["waitingReason"] is None


def test_projection_marks_human_identity_from_binding_not_waiting_status(
    tmp_path: Path,
) -> None:
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
    )
    waiting = runner.start({"goal": "ship the release"})

    projection = build_run_projection(
        runner.ledger,
        waiting["id"],
        binding=runner._binding,
    )
    node = next(item for item in projection["nodes"] if item["nodeId"] == "review")

    assert node["type"] == "call"
    assert node["execution"]["participantType"] == "human"
    assert node["execution"]["executorRef"] == "builtin.human-review.v1"


def test_http_job_adapter_does_not_claim_the_remote_participant_type() -> None:
    slot = SimpleNamespace(
        adapter="http_job",
        executor_ref="remote.executor.v1",
        config={"baseUrl": "https://agent.example.test/jobs"},
    )

    execution = _execution_summary(
        slot,
        {"type": "call"},
        human_request=None,
    )

    assert execution is not None
    assert execution["participantType"] == "unknown"
    assert execution["adapter"] == "http_job"
    assert execution["location"] == "external"
    assert execution["target"] == "外部服务 · agent.example.test"


def test_waiting_reason_requires_a_persisted_wait_or_active_child_scope() -> None:
    invocation = {"status": "waiting"}

    assert _waiting_reason(
        {"status": "planned"},
        human_request=None,
        waits=[{"kind": "external-submit", "invocation_id": "inv-1"}],
        child_scopes=[],
        node_type="call",
        invocation_id="inv-1",
    ) == "等待提交确认"
    assert _waiting_reason(
        invocation,
        human_request=None,
        waits=[],
        child_scopes=[],
        node_type="call",
    ) is None
    assert _waiting_reason(
        invocation,
        human_request=None,
        waits=[{"kind": "external-observe", "invocation_id": "inv-1"}],
        child_scopes=[],
        node_type="call",
        invocation_id="inv-1",
    ) == "等待外部服务"
    assert _waiting_reason(
        {"status": "running"},
        human_request=None,
        waits=[],
        child_scopes=[{"status": "active", "path_json": '["root","repeat","2"]'}],
        node_type="repeat",
        invocation_id="inv-2",
    ) == "等待第 2 轮子流程完成"


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

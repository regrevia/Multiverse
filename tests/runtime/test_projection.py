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

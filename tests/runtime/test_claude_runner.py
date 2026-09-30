from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ruamel.yaml import YAML

from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry
from multiverse_workflow.runtime.runner import Runner

ROOT = Path(__file__).parents[2]


def test_claude_fixture_runs_through_runtime_verifier_to_human_request(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "claude"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "if '--version' in sys.argv:\n"
        "    print('fixture')\n"
        "    raise SystemExit(0)\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'result','subtype':'success',"
        "'result':'{\\\"text\\\":\\\"claude runtime fixture\\\","
        "\\\"artifact_refs\\\":[]}', 'session_id':'fixture-session'}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    binding = YAML(typ="safe").load(
        (ROOT / "examples/bindings/content-local.yaml").read_text(encoding="utf-8")
    )
    producer = binding["spec"]["slots"]["producer"]
    producer["adapter"] = "claude"
    producer["executorRef"] = "builtin.claude-deliverable.v1"
    producer["config"] = {
        "cwd": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(tmp_path),
        "command": [str(fake)],
        "expectedVersion": "fixture",
        "artifactName": "claude-fixture.md",
        "artifactMediaType": "text/markdown",
    }
    binding_path = tmp_path / "binding.yaml"
    with binding_path.open("w", encoding="utf-8") as stream:
        YAML().dump(binding, stream)
    registry = ExecutorRegistry(
        [
            replace(descriptor, verified=True)
            if descriptor.executor_ref == "builtin.claude-deliverable.v1"
            else descriptor
            for descriptor in local_executor_registry().descriptors()
        ]
    )
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=binding_path,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )
    try:
        waiting = runner.start({"goal": "produce a fixture deliverable"})
        assert waiting["status"] == "waiting", (
            waiting.get("error_json"),
            runner.ledger.list_attempts(waiting["id"]),
        )
        attempts = runner.ledger.list_attempts(waiting["id"])
        assert [item["status"] for item in attempts] == [
            "succeeded",
            "succeeded",
            "succeeded",
            "waiting",
        ]
        artifact = runner.ledger.list_artifacts(run_id=waiting["id"])[0]
        assert artifact["name"] == "claude-fixture.md"
        assert artifact["status"] == "ready"
        assert Path(artifact["storage_ref"]).read_bytes() == b"claude runtime fixture"
        request = runner.pending_human_requests(waiting["id"])[0]
        assert json.loads(request["input_json"])["deliverable"]["artifact_refs"] == [
            artifact["id"]
        ]
        assert runner.ledger.get_run(waiting["id"])["current_node_id"] == "review"
    finally:
        runner.close()

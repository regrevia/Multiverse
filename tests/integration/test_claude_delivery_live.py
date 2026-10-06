from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry
from multiverse_workflow.runtime.runner import Runner

pytestmark = pytest.mark.integration


def test_real_cc_switch_claude_runs_to_runtime_human_request(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CLAUDE_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CLAUDE_LIVE=1 to run the Claude delivery probe")
    if shutil.which("claude") is None:
        pytest.fail("claude executable is required for the Claude delivery probe")

    binding = YAML(typ="safe").load(
        (Path(__file__).parents[2] / "examples/bindings/content-claude.yaml").read_text(
            encoding="utf-8"
        )
    )
    producer = binding["spec"]["slots"]["producer"]
    producer["config"] = {
        **producer["config"],
        "cwd": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(Path.home()),
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
        Path(__file__).parents[2] / "presets/content-delivery",
        binding_path=binding_path,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )
    try:
        waiting = runner.start(
            {"goal": "Write one concise release note for the Multiverse runtime."}
        )
        assert waiting["status"] == "waiting"
        request = runner.pending_human_requests(waiting["id"])[0]
        attempts = runner.ledger.list_attempts(waiting["id"])
        artifacts = runner.ledger.list_artifacts(run_id=waiting["id"])
        assert len(attempts) == 4
        assert [attempt["status"] for attempt in attempts] == [
            "succeeded",
            "succeeded",
            "succeeded",
            "waiting",
        ]
        assert artifacts and artifacts[0]["status"] == "ready"
        assert request["authorized_subjects_json"] == '["example-reviewer"]'
        print(
            f"claude_cc_switch_live_run_id={waiting['id']} "
            f"request_id={request['id']} artifact_id={artifacts[0]['id']} "
            f"artifact_digest={artifacts[0]['digest']} attempt_ids="
            f"{[attempt['id'] for attempt in attempts]}"
        )
    finally:
        runner.close()

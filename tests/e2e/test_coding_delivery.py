from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from multiverse_workflow.runtime.executors import execute_codex
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry
from multiverse_workflow.runtime.runner import Runner

pytestmark = pytest.mark.integration


def _live_registry() -> ExecutorRegistry:
    return ExecutorRegistry(
        [
            replace(descriptor, verified=True)
            if descriptor.executor_ref == "builtin.codex-deliverable.v1"
            else descriptor
            for descriptor in local_executor_registry().descriptors()
        ]
    )


def _write_live_binding(tmp_path: Path) -> Path:
    binding = YAML(typ="safe").load(
        (Path(__file__).parents[2] / "examples/bindings/content-local.yaml").read_text()
    )
    producer = binding["spec"]["slots"]["producer"]
    producer["adapter"] = "codex"
    producer["executorRef"] = "builtin.codex-deliverable.v1"
    producer["config"] = {
        "cwd": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
        "interactionAuthorizedSubjects": ["example-reviewer"],
        "model": os.environ.get("MULTIVERSE_CODEX_MODEL", "gpt-5.5"),
        "systemPrompt": (
            "Return only concise JSON with a non-empty text field and an empty "
            "artifact_refs array. Do not use tools or invent Artifact IDs."
        ),
        "artifactName": "codex-runtime-deliverable.md",
        "artifactMediaType": "text/markdown",
        "timeoutSeconds": 180,
    }
    binding_path = tmp_path / "binding.yaml"
    with binding_path.open("w", encoding="utf-8") as handle:
        YAML().dump(binding, handle)
    return binding_path


def test_real_coding_delivery_probe_reaches_runtime_shaped_output(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized local Codex probe")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the coding delivery probe")

    result = execute_codex(
        {
            "goal": (
                "Prepare a concise release note for Multiverse. "
                "Return a useful human-reviewable deliverable."
            )
        },
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
            "model": os.environ.get("MULTIVERSE_CODEX_MODEL", "gpt-5.5"),
            "systemPrompt": (
                "Act as the producer node for a human-reviewed delivery workflow. "
                "Return only JSON with non-empty text and an empty artifact_refs array."
            ),
            "artifactName": "coding-delivery-probe.md",
            "artifactMediaType": "text/markdown",
            "timeoutSeconds": 180,
        },
    )

    assert result.generated_artifact is not None
    assert result.output["artifact_refs"] == []
    assert result.observations


def test_real_coding_delivery_completes_runtime_human_loop(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized local Codex loop")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the coding delivery loop")

    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    runner = Runner(
        Path(__file__).parents[2] / "presets/content-delivery",
        binding_path=binding_path,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )

    try:
        waiting = runner.start(
            {"goal": "Write a concise release note for the Multiverse runtime."}
        )
        assert waiting["status"] == "waiting"
        request = runner.pending_human_requests(waiting["id"])[0]
        assert request["authorized_subjects_json"] == '["example-reviewer"]'
        artifacts = runner.ledger.list_artifacts(run_id=waiting["id"])
        assert artifacts and artifacts[0]["status"] == "ready"

        finished = runner.decide(
            request["id"],
            choice="approve",
            comment="Approved by the authorized reviewer.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-e2e",
        )

        assert finished["status"] == "succeeded"
        output = json.loads(finished["output_json"])
        assert output["review"]["decision"] == "approve"
        assert output["deliverable"]["artifact_refs"]
    finally:
        runner.close()


def test_real_coding_delivery_survives_runtime_restart_before_approval(
    tmp_path: Path,
) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized restart loop")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the restart loop")

    package = Path(__file__).parents[2] / "presets/content-delivery"
    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    database = tmp_path / "runtime.db"
    runner = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    waiting = runner.start({"goal": "Write a concise release note for Multiverse."})
    assert waiting["status"] == "waiting"
    run_id = waiting["id"]
    original_requests = runner.pending_human_requests(run_id)
    assert len(original_requests) == 1
    original_request_id = original_requests[0]["id"]
    before_attempts = len(runner.ledger.list_attempts(run_id))
    before_artifacts = len(runner.ledger.list_artifacts(run_id=run_id))
    runner.close()

    restarted = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    try:
        recovered_requests = restarted.pending_human_requests(run_id)
        assert len(recovered_requests) == 1
        request = recovered_requests[0]
        assert request["id"] == original_request_id
        print(f"restart_e2e_run_id={run_id}")
        finished = restarted.decide(
            request["id"],
            choice="approve",
            comment="Approved after runtime restart.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-restart-approve",
        )
        assert finished["status"] == "succeeded"
        assert len(restarted.ledger.list_attempts(run_id)) == before_attempts
        assert len(restarted.ledger.list_artifacts(run_id=run_id)) == before_artifacts
        replay = restarted.decide(
            request["id"],
            choice="approve",
            comment="Approved after runtime restart.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-restart-approve",
        )
        assert replay["status"] == "succeeded"
        assert len(restarted.ledger.list_attempts(run_id)) == before_attempts
    finally:
        restarted.close()

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from multiverse_workflow.runtime.executors import ExecutionResult, GeneratedArtifact
from multiverse_workflow.runtime.ledger import LedgerConflict
from multiverse_workflow.runtime.registry import (
    ExecutorDescriptor,
    ExecutorRegistry,
    local_executor_registry,
)
from multiverse_workflow.runtime.runner import RunError, Runner

ROOT = Path(__file__).parents[2]


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

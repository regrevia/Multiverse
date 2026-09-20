import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from multiverse_workflow.runtime.ledger import LedgerConflict
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

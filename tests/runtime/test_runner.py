import json
from pathlib import Path

from multiverse_workflow.runtime.runner import Runner

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

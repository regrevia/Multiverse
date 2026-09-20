import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multiverse_workflow.cli.main import app
from multiverse_workflow.runtime.ledger import Ledger
from multiverse_workflow.runtime.runner import Runner

ROOT = Path(__file__).parents[2]
CLI = CliRunner()


def test_run_inspect_and_decide_commands_drive_local_runtime(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    run_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--input",
            str(ROOT / "presets/content-delivery/evals/cases.jsonl"),
            "--db",
            str(database),
            "--json",
        ],
    )

    assert run_result.exit_code == 2

    request_input = tmp_path / "request.json"
    request_input.write_text(json.dumps({"goal": "ship the release"}), encoding="utf-8")
    run_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--input",
            str(request_input),
            "--db",
            str(database),
            "--json",
        ],
    )
    assert run_result.exit_code == 4, run_result.stdout
    waiting = json.loads(run_result.stdout)
    assert waiting["status"] == "waiting"

    inspect_result = CLI.invoke(
        app,
        ["inspect", waiting["id"], "--db", str(database), "--json"],
    )
    assert inspect_result.exit_code == 0
    assert json.loads(inspect_result.stdout)["status"] == "waiting"

    request = Ledger(database).list_human_requests(status="pending")[0]
    decide_result = CLI.invoke(
        app,
        [
            "decide",
            request["id"],
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--db",
            str(database),
            "--choice",
            "approve",
            "--subject-digest",
            request["subject_digest"],
            "--expected-version",
            str(request["version"]),
            "--json",
        ],
    )

    assert decide_result.exit_code == 0, decide_result.stdout
    assert json.loads(decide_result.stdout)["status"] == "succeeded"


def test_cli_submits_a_structured_human_decision_file(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    request_input = tmp_path / "request.json"
    request_input.write_text(json.dumps({"goal": "ship the release"}), encoding="utf-8")
    run_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--input",
            str(request_input),
            "--db",
            str(database),
            "--json",
        ],
    )
    assert run_result.exit_code == 4, run_result.stdout
    waiting = json.loads(run_result.stdout)
    request = Ledger(database).list_human_requests(status="pending")[0]
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps({"decision": "approve", "comment": "Approved."}),
        encoding="utf-8",
    )

    result = CLI.invoke(
        app,
        [
            "decide",
            request["id"],
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--db",
            str(database),
            "--decision-file",
            str(decision_file),
            "--subject-digest",
            request["subject_digest"],
            "--expected-version",
            str(request["version"]),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["id"] == waiting["id"]


def test_cli_worker_once_processes_pending_progress_intent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "runtime.db"
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=database,
    )
    waiting = runner.start({"goal": "ship the release"})
    request = runner.pending_human_requests(waiting["id"])[0]
    original_drive = runner._drive
    monkeypatch.setattr(
        runner,
        "_drive",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated worker interruption")
        ),
    )
    try:
        with pytest.raises(RuntimeError, match="simulated worker interruption"):
            runner.decide(
                request["id"],
                choice="approve",
                comment="Approved.",
                actor="example-reviewer",
                subject_digest=request["subject_digest"],
                expected_version=request["version"],
                idempotency_key="cli-worker-recovery",
            )
    finally:
        monkeypatch.setattr(runner, "_drive", original_drive)
        runner.close()

    result = CLI.invoke(
        app,
        [
            "worker",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--db",
            str(database),
            "--worker-id",
            "cli-worker",
            "--once",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["cycles"] == 1
    assert payload["workerId"] == "cli-worker"
    assert payload["processed"][0]["run_id"] == waiting["id"]
    assert Ledger(database).get_run(waiting["id"])["status"] == "succeeded"


def test_cli_pause_resume_and_cancel_commands_use_run_versions(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    request_input = tmp_path / "request.json"
    request_input.write_text(json.dumps({"goal": "ship the release"}), encoding="utf-8")
    waiting_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--input",
            str(request_input),
            "--db",
            str(database),
            "--json",
        ],
    )
    waiting = json.loads(waiting_result.stdout)

    pause_result = CLI.invoke(
        app,
        [
            "pause",
            waiting["id"],
            "--db",
            str(database),
            "--expected-version",
            str(waiting["version"]),
            "--reason",
            "Wait for the release window.",
            "--json",
        ],
    )
    paused = json.loads(pause_result.stdout)
    resume_result = CLI.invoke(
        app,
        [
            "resume",
            paused["id"],
            "--package",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--db",
            str(database),
            "--expected-version",
            str(paused["version"]),
            "--reason",
            "Release window is open.",
            "--json",
        ],
    )
    resumed = json.loads(resume_result.stdout)
    cancel_result = CLI.invoke(
        app,
        [
            "cancel",
            resumed["id"],
            "--db",
            str(database),
            "--expected-version",
            str(resumed["version"]),
            "--reason",
            "Release was withdrawn.",
            "--json",
        ],
    )

    assert pause_result.exit_code == 0, pause_result.stdout
    assert paused["status"] == "paused"
    assert resume_result.exit_code == 0, resume_result.stdout
    assert resumed["status"] == "waiting"
    assert cancel_result.exit_code == 0, cancel_result.stdout
    assert json.loads(cancel_result.stdout)["status"] == "cancelled"


def test_cli_inspect_graph_exports_a_runtime_projection(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    request_input = tmp_path / "request.json"
    request_input.write_text(json.dumps({"goal": "ship the release"}), encoding="utf-8")
    run_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--input",
            str(request_input),
            "--db",
            str(database),
            "--json",
        ],
    )
    waiting = json.loads(run_result.stdout)

    result = CLI.invoke(
        app,
        ["inspect", waiting["id"], "--db", str(database), "--graph", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    projection = json.loads(result.stdout)
    assert projection["protocolVersion"] == "multiverse/v0.1"
    assert projection["run"]["id"] == waiting["id"]
    assert projection["nodes"]


def test_cli_runs_manual_input_artifact_trial_end_to_end(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    request_input = tmp_path / "request.json"
    request_input.write_text(json.dumps({"goal": "prepare a release"}), encoding="utf-8")
    run_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/manual-input"),
            "--binding",
            str(ROOT / "examples/bindings/manual-input-local.yaml"),
            "--input",
            str(request_input),
            "--db",
            str(database),
            "--json",
        ],
    )
    assert run_result.exit_code == 4, run_result.stdout
    waiting = json.loads(run_result.stdout)
    request = Ledger(database).list_human_requests(status="pending")[0]

    deliverable = tmp_path / "release.md"
    deliverable.write_text("# Release\n", encoding="utf-8")
    artifact_result = CLI.invoke(
        app,
        [
            "artifact",
            "register",
            waiting["id"],
            "--file",
            str(deliverable),
            "--request-id",
            request["id"],
            "--media-type",
            "text/markdown",
            "--db",
            str(database),
            "--json",
        ],
    )
    assert artifact_result.exit_code == 0, artifact_result.stdout
    artifact = json.loads(artifact_result.stdout)

    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "artifact_refs": [artifact["id"]],
                "change_summary": "Prepared the release document.",
            }
        ),
        encoding="utf-8",
    )
    decide_result = CLI.invoke(
        app,
        [
            "decide",
            request["id"],
            str(ROOT / "presets/manual-input"),
            "--binding",
            str(ROOT / "examples/bindings/manual-input-local.yaml"),
            "--db",
            str(database),
            "--decision-file",
            str(decision_file),
            "--subject-digest",
            request["subject_digest"],
            "--expected-version",
            str(request["version"]),
            "--actor",
            "example-editor",
            "--json",
        ],
    )

    assert decide_result.exit_code == 0, decide_result.stdout
    finished = json.loads(decide_result.stdout)
    assert finished["status"] == "succeeded"
    assert json.loads(finished["output_json"])["artifact_refs"] == [artifact["id"]]


def test_cli_sweep_resumes_a_persisted_human_progress_intent(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    request_input = tmp_path / "request.json"
    request_input.write_text(json.dumps({"goal": "ship the release"}), encoding="utf-8")
    run_result = CLI.invoke(
        app,
        [
            "run",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--input",
            str(request_input),
            "--db",
            str(database),
            "--json",
        ],
    )
    assert run_result.exit_code == 4, run_result.stdout
    waiting = json.loads(run_result.stdout)
    ledger = Ledger(database)
    request = ledger.list_human_requests(status="pending")[0]
    ledger.decide_human_request(
        request["id"],
        choice="approve",
        comment="Approved.",
        actor="example-reviewer",
        subject_digest=request["subject_digest"],
        expected_version=request["version"],
        idempotency_key="decision-cli-sweep",
    )

    result = CLI.invoke(
        app,
        [
            "sweep",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--db",
            str(database),
            "--worker-id",
            "cli-worker",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload[0]["run_id"] == waiting["id"]
    assert Ledger(database).get_run(waiting["id"])["status"] == "succeeded"

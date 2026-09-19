import json
from pathlib import Path

from typer.testing import CliRunner

from multiverse_workflow.cli.main import app
from multiverse_workflow.runtime.ledger import Ledger

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

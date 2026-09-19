import json
from pathlib import Path

from typer.testing import CliRunner

from multiverse_workflow.cli.main import app

ROOT = Path(__file__).parents[2]


def test_validate_json_returns_a_serializable_execution_plan() -> None:
    result = CliRunner().invoke(
        app,
        [
            "validate",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["plans"]["delivery"]["compiledPlanDigest"].startswith("sha256:")
    assert payload["diagnostics"] == []


def test_validate_json_returns_diagnostics_and_exit_code_two() -> None:
    result = CliRunner().invoke(
        app,
        ["validate", str(ROOT / "tests/fixtures/invalid/dangling-edge"), "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "INVALID_EDGE"


def test_capabilities_command_reports_support_levels() -> None:
    result = CliRunner().invoke(app, ["capabilities", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["protocolVersion"] == "multiverse/v0.1"
    by_id = {item["executorRef"]: item for item in payload["executors"]}
    assert by_id["builtin.human-input.v1"]["declared"] is True
    assert by_id["builtin.human-input.v1"]["available"] is True
    assert by_id["example.remote-content.v1"]["declared"] is True
    assert by_id["example.remote-content.v1"]["available"] is False
    assert by_id["example.remote-content.v1"]["verified"] is False

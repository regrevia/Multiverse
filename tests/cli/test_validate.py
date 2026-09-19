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

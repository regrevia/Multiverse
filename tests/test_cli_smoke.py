from typer.testing import CliRunner

from multiverse_workflow.cli.main import app


def test_cli_exposes_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.stdout

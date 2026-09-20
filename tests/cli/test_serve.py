from typer.testing import CliRunner

from multiverse_workflow.cli.main import app


def test_serve_help_describes_local_service_without_starting_runtime() -> None:
    result = CliRunner().invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "--db" in result.stdout
    assert "--package" in result.stdout
    assert "--binding" in result.stdout
    assert "--port" in result.stdout
    assert "--subject" in result.stdout

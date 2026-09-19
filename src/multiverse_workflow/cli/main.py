import json
from pathlib import Path
from typing import Annotated

import typer

from multiverse_workflow import __version__
from multiverse_workflow.compiler import compile_package

app = typer.Typer(add_completion=False, no_args_is_help=True)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Validate and run Multiverse Workflow packages."""


@app.command()
def validate(
    package: Annotated[Path, typer.Argument(exists=False, file_okay=False)],
    binding: Annotated[Path | None, typer.Option("--binding")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check a package and produce a deterministic execution plan."""
    result = compile_package(package, binding_path=binding)
    payload = {
        "ok": result.ok,
        "plans": {workflow_id: plan.as_dict() for workflow_id, plan in result.plans.items()},
        "diagnostics": [diagnostic.as_dict() for diagnostic in result.diagnostics],
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    elif result.ok:
        typer.echo(f"validated {package}")
        for workflow_id, plan in result.plans.items():
            typer.echo(f"  {workflow_id}: {plan.compiled_plan_digest}")
    else:
        for diagnostic in result.diagnostics:
            typer.echo(
                f"{diagnostic.code}: {diagnostic.file}{diagnostic.pointer} {diagnostic.message}",
                err=True,
            )
    if not result.ok:
        raise typer.Exit(code=2)

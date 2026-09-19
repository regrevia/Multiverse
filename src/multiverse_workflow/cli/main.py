import json
from pathlib import Path
from typing import Annotated

import typer

from multiverse_workflow import __version__
from multiverse_workflow.compiler import compile_package
from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.runtime.runner import RunError, Runner

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


@app.command("run")
def run(
    package: Annotated[Path, typer.Argument(exists=False, file_okay=False)],
    binding: Annotated[Path, typer.Option("--binding", exists=True, dir_okay=False)],
    input_file: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    workflow: Annotated[str | None, typer.Option("--workflow")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run one workflow in the local SQLite runtime."""
    try:
        input_value = json.loads(input_file.read_text(encoding="utf-8"))
        runner = Runner(package, binding_path=binding, database_path=db)
        run_record = runner.start(input_value, workflow_id=workflow)
    except (OSError, json.JSONDecodeError, RunError) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=2) from exc
    _emit_record(run_record, as_json)
    if run_record["status"] == "waiting":
        raise typer.Exit(code=4)
    if run_record["status"] == "failed":
        raise typer.Exit(code=1)


@app.command()
def inspect(
    run_id: Annotated[str, typer.Argument()],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect one persisted local run."""
    record = Ledger(db).get_run(run_id)
    if record is None:
        _emit_error(f"run not found: {run_id}", as_json)
        raise typer.Exit(code=2)
    _emit_record(record, as_json)


@app.command()
def decide(
    request_id: Annotated[str, typer.Argument()],
    package: Annotated[Path, typer.Argument(exists=False, file_okay=False)],
    binding: Annotated[Path, typer.Option("--binding", exists=True, dir_okay=False)],
    choice: Annotated[str, typer.Option("--choice")],
    subject_digest: Annotated[str, typer.Option("--subject-digest")],
    expected_version: Annotated[int, typer.Option("--expected-version")],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    comment: Annotated[str, typer.Option("--comment")] = "",
    actor: Annotated[str, typer.Option("--actor")] = "example-reviewer",
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Submit one authorized human decision and resume its run."""
    try:
        runner = Runner(package, binding_path=binding, database_path=db)
        record = runner.decide(
            request_id,
            choice=choice,
            comment=comment,
            actor=actor,
            subject_digest=subject_digest,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except LedgerConflict as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=3) from exc
    except (OSError, RunError, KeyError) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=2) from exc
    _emit_record(record, as_json)
    if record["status"] == "failed":
        raise typer.Exit(code=1)


def _emit_record(record: dict[str, object], as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(record, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(f"{record['id']}: {record['status']}")


def _emit_error(message: str, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        typer.echo(message, err=True)

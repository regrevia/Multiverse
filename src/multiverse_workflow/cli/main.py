import json
from pathlib import Path
from typing import Annotated

import typer

from multiverse_workflow import __version__
from multiverse_workflow.compiler import compile_package, executor_capabilities
from multiverse_workflow.runtime.ledger import Ledger, LedgerConflict
from multiverse_workflow.runtime.runner import RunError, Runner

app = typer.Typer(add_completion=False, no_args_is_help=True)
artifact_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(artifact_app, name="artifact")


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


@app.command()
def capabilities(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List local executor capabilities and their support states."""
    payload = {
        "protocolVersion": "multiverse/v0.1",
        "scope": "local",
        "executors": executor_capabilities(),
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    for executor in executor_capabilities():
        status = ", ".join(
            f"{key}={str(executor[key]).lower()}"
            for key in ("declared", "installed", "available", "verified")
        )
        typer.echo(f"{executor['executorRef']}: {status}")


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
def pause(
    run_id: Annotated[str, typer.Argument()],
    expected_version: Annotated[int, typer.Option("--expected-version")],
    reason: Annotated[str, typer.Option("--reason")],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Pause new local dispatch for a Run."""
    try:
        record = Ledger(db).control_run(
            run_id,
            operation="pause",
            expected_version=expected_version,
            reason=reason,
        )
    except (KeyError, LedgerConflict) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=3) from exc
    _emit_record(record, as_json)


@app.command()
def resume(
    run_id: Annotated[str, typer.Argument()],
    package: Annotated[Path, typer.Option("--package", exists=True, file_okay=False)],
    binding: Annotated[Path, typer.Option("--binding", exists=True, dir_okay=False)],
    expected_version: Annotated[int, typer.Option("--expected-version")],
    reason: Annotated[str, typer.Option("--reason")],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Resume local dispatch for a paused Run."""
    try:
        record = Runner(package, binding_path=binding, database_path=db).resume(
            run_id,
            expected_version=expected_version,
            reason=reason,
        )
    except LedgerConflict as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=3) from exc
    except (KeyError, RunError) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=2) from exc
    _emit_record(record, as_json)


@app.command()
def cancel(
    run_id: Annotated[str, typer.Argument()],
    expected_version: Annotated[int, typer.Option("--expected-version")],
    reason: Annotated[str, typer.Option("--reason")],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Cancel a local Run that has no active external Attempt."""
    try:
        record = Ledger(db).control_run(
            run_id,
            operation="cancel",
            expected_version=expected_version,
            reason=reason,
        )
    except (KeyError, LedgerConflict) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=3) from exc
    _emit_record(record, as_json)


@app.command()
def rerun(
    run_id: Annotated[str, typer.Argument()],
    package: Annotated[Path, typer.Option("--package", exists=True, file_okay=False)],
    binding: Annotated[Path, typer.Option("--binding", exists=True, dir_okay=False)],
    reason: Annotated[str, typer.Option("--reason")],
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a separate local Run from a terminal Run's frozen input."""
    try:
        record = Runner(package, binding_path=binding, database_path=db).rerun(
            run_id,
            reason=reason,
        )
    except LedgerConflict as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=3) from exc
    except (KeyError, RunError) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=2) from exc
    _emit_record(record, as_json)
    if record["status"] == "waiting":
        raise typer.Exit(code=4)
    if record["status"] == "failed":
        raise typer.Exit(code=1)


@app.command()
def decide(
    request_id: Annotated[str, typer.Argument()],
    package: Annotated[Path, typer.Argument(exists=False, file_okay=False)],
    binding: Annotated[Path, typer.Option("--binding", exists=True, dir_okay=False)],
    subject_digest: Annotated[str, typer.Option("--subject-digest")],
    expected_version: Annotated[int, typer.Option("--expected-version")],
    choice: Annotated[str | None, typer.Option("--choice")] = None,
    decision_file: Annotated[Path | None, typer.Option("--decision-file")] = None,
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    comment: Annotated[str, typer.Option("--comment")] = "",
    actor: Annotated[str, typer.Option("--actor")] = "example-reviewer",
    idempotency_key: Annotated[str | None, typer.Option("--idempotency-key")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Submit one authorized human decision and resume its run."""
    try:
        if choice is not None and decision_file is not None:
            raise RunError("use either --choice or --decision-file, not both")
        decision: object | None = None
        if decision_file is not None:
            decision = json.loads(decision_file.read_text(encoding="utf-8"))
        runner = Runner(package, binding_path=binding, database_path=db)
        record = runner.decide(
            request_id,
            choice=choice,
            decision=decision,
            comment=comment,
            actor=actor,
            subject_digest=subject_digest,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except LedgerConflict as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=3) from exc
    except (OSError, json.JSONDecodeError, RunError, KeyError) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=2) from exc
    _emit_record(record, as_json)
    if record["status"] == "failed":
        raise typer.Exit(code=1)


@artifact_app.command("register")
def register_artifact(
    run_id: Annotated[str, typer.Argument()],
    file: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False)],
    name: Annotated[str | None, typer.Option("--name")] = None,
    media_type: Annotated[str, typer.Option("--media-type")] = "application/octet-stream",
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    db: Annotated[Path, typer.Option("--db")] = Path(".multiverse/runtime.db"),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Register a completed local file as an immutable ArtifactRef."""
    ledger = Ledger(db)
    try:
        invocation_id = None
        if request_id is not None:
            request = ledger.get_human_request(request_id)
            if request is None or request["run_id"] != run_id:
                raise LedgerConflict("request is not part of run")
            invocation_id = request["invocation_id"]
        artifact = ledger.register_artifact(
            run_id=run_id,
            source_path=file,
            name=name or file.name,
            media_type=media_type,
            invocation_id=invocation_id,
        )
    except (OSError, KeyError, LedgerConflict) as exc:
        _emit_error(str(exc), as_json)
        raise typer.Exit(code=2) from exc
    _emit_record(artifact, as_json)


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

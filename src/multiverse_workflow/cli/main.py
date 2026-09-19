from typing import Annotated

import typer

from multiverse_workflow import __version__

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


import typer

from job_terminal_models import Job  # noqa: F401

app = typer.Typer(add_completion=False, help="Title-field pipeline commands.")


@app.command("filter")
def filter() -> None:
    """Stub: filter job titles. Not implemented yet."""
    typer.echo("title filter: not implemented")

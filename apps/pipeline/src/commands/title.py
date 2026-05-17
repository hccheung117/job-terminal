import typer

from db import build_engine
from steps.filter_title import (
    execute_filter_title_plan,
    plan_filter_title,
    render_filter_title_plan,
)

app = typer.Typer(add_completion=False, help="Title-field pipeline commands.")


@app.command("filter")
def filter(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report the title_filter decisions that would be written, without writing to the database.",
    ),
) -> None:
    """Reject jobs whose titles match a stopword and write title_filter decisions."""
    engine = build_engine()
    plans = plan_filter_title(engine)

    if not plans:
        typer.echo("No jobs would be rejected by title filter. Nothing to do.")
        return

    if dry_run:
        render_filter_title_plan(plans)
        typer.echo(f"[dry-run] {len(plans)} title_filter decision(s) would be written")
        return

    render_filter_title_plan(plans)
    written = execute_filter_title_plan(engine, plans)
    typer.echo(f"{written} title_filter decision(s) written")

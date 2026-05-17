import typer

from db import build_engine
from steps.filter_title import (
    execute_filter_title_plan,
    plan_filter_title,
    render_filter_title_plan,
)
from steps.judge_title import (
    execute_judge_title_plan,
    plan_judge_title,
    render_judge_title_plan,
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
    """Audit jobs against stopwords and write title_filter pass/reject decisions."""
    engine = build_engine()
    plans = plan_filter_title(engine)

    if not plans:
        typer.echo("No new title_filter decisions to write. Nothing to do.")
        return

    if dry_run:
        render_filter_title_plan(plans)
        typer.echo(f"[dry-run] {len(plans)} title_filter decision(s) would be written")
        return

    render_filter_title_plan(plans)
    written = execute_filter_title_plan(engine, plans)
    typer.echo(f"{written} title_filter decision(s) written")


@app.command("judge")
def judge(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report the title_judge pairs that would be judged, without calling Gemini or writing to the database.",
    ),
) -> None:
    """Judge surviving titles against each user's criteria and write title_judge decisions."""
    engine = build_engine()
    plans = plan_judge_title(engine)

    if not plans:
        typer.echo("No new title_judge candidates. Nothing to do.")
        return

    render_judge_title_plan(plans)

    if dry_run:
        typer.echo(f"[dry-run] {len(plans)} title_judge pair(s) would be judged")
        return

    written = execute_judge_title_plan(engine, plans)
    typer.echo(f"{written} title_judge decision(s) written")

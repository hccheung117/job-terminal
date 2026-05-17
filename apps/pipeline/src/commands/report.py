import typer

from db import build_engine
from steps.report import (
    execute_report_plan,
    plan_report,
    render_report_preview,
)


def report(
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Print the markdown email draft for each user instead of sending.",
    ),
) -> None:
    """Report the jobs each user has not been filtered out of, so far."""
    engine = build_engine()
    reports = plan_report(engine)

    if preview:
        render_report_preview(reports)
        return

    sent = execute_report_plan(engine, reports)
    typer.echo(f"{sent} report(s) sent")

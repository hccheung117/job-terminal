import typer
from rich.console import Console
from rich.markdown import Markdown

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
        markdown = render_report_preview(reports)
        if markdown:
            Console().print(Markdown(markdown))
        return

    result = execute_report_plan(engine, reports)
    for failure in result.failures:
        typer.echo(
            f"Failed to send report for user {failure.user_id}: {failure.message}",
            err=True,
        )
    typer.echo(f"{result.sent} report(s) sent")
    if result.failures:
        raise typer.Exit(code=1)

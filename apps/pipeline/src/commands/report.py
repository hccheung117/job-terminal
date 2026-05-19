import typer
from job_terminal_tui import TuiFormatter
from rich.console import Console
from rich.markdown import Markdown

from db import build_engine
from steps.report import (
    execute_report_plan,
    plan_report,
    render_report_preview,
)

_console = Console()
_err_console = Console(stderr=True)


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
        fmt = TuiFormatter()
        fmt.error(f"Failed to send report for user {failure.user_id}: {failure.message}")
        _err_console.print(fmt.render())
    fmt = TuiFormatter()
    fmt.success(f"{result.sent} report(s) sent")
    _console.print(fmt.render())
    if result.failures:
        raise typer.Exit(code=1)

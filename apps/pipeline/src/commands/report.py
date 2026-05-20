import re
import subprocess
import tempfile
from pathlib import Path

import typer
from job_terminal_tui import TuiFormatter
from rich.console import Console

from db import build_engine
from paths import INSIGHTS_DIR
from steps.insight import apply_insights
from steps.report import (
    execute_report_plan,
    plan_report,
    render_report_previews,
)

_console = Console()
_err_console = Console(stderr=True)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "user"


def report(
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Render each user's email HTML into a temp folder and open it.",
    ),
) -> None:
    """Report the jobs each user has not been filtered out of, so far."""
    engine = build_engine()
    reports = plan_report(engine)
    apply_insights(reports, cache_dir=INSIGHTS_DIR)

    if preview:
        previews = render_report_previews(reports)
        if not previews:
            fmt = TuiFormatter()
            fmt.info("No emails to preview")
            _console.print(fmt.render())
            return
        folder = Path(tempfile.mkdtemp(prefix="job-terminal-preview-"))
        for user_report, html in previews:
            name = f"{_slugify(user_report.user_name)}-{user_report.user_id}.html"
            (folder / name).write_text(html)
        subprocess.run(["open", str(folder)], check=False)
        fmt = TuiFormatter()
        fmt.success(f"{len(previews)} email(s) rendered to {folder}")
        _console.print(fmt.render())
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

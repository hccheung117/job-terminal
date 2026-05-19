from uuid import UUID

import typer
from job_terminal_tui import TuiFormatter
from rich.console import Console

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
_console = Console()
_err_console = Console(stderr=True)


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
    output = plan_filter_title(engine)
    plans = output.plans

    for warning in output.warnings:
        fmt = TuiFormatter()
        fmt.info(f"warning: {warning}")
        _err_console.print(fmt.render())

    if not plans:
        typer.echo("No new title_filter decisions to write. Nothing to do.")
        return

    report = render_filter_title_plan(plans)
    if report:
        _err_console.print(report)

    if dry_run:
        fmt = TuiFormatter()
        fmt.info(f"[dry-run] {len(plans)} title_filter decision(s) would be written")
        _err_console.print(fmt.render())
        return

    written = execute_filter_title_plan(engine, plans)
    fmt = TuiFormatter()
    fmt.success(f"{written} title_filter decision(s) written")
    _console.print(fmt.render())


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

    if dry_run:
        report = render_judge_title_plan(plans)
        if report:
            _err_console.print(report)
        fmt = TuiFormatter()
        fmt.info(f"[dry-run] {len(plans)} title_judge pair(s) would be judged")
        _err_console.print(fmt.render())
        return

    fmt = TuiFormatter()
    fmt.info(f"Judging {len(plans)} title_judge candidate(s)")
    _err_console.print(fmt.render())

    current_user_id: UUID | None = None
    written = 0
    for result in execute_judge_title_plan(engine, plans):
        p = result.plan
        if p.user_id != current_user_id:
            header_fmt = TuiFormatter()
            header_fmt.header(f"{p.user_name} ({TuiFormatter.dim(p.user_email)})")
            _err_console.print(header_fmt.render())
            current_user_id = p.user_id
        line_fmt = TuiFormatter()
        if result.passes:
            line_fmt.success(p.title, indent=2)
        else:
            line_fmt.rejected_with_reason(p.title, result.reason, indent=2)
        _err_console.print(line_fmt.render())
        written += 1

    summary_fmt = TuiFormatter()
    summary_fmt.success(f"{written} title_judge decision(s) written")
    _console.print(summary_fmt.render())

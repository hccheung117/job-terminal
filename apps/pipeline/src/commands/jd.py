from uuid import UUID

import typer
from job_terminal_tui import TuiFormatter
from rich.console import Console

from db import build_engine
from steps.judge_jd import (
    execute_judge_jd_plan,
    plan_judge_jd,
    render_judge_jd_plan,
)

app = typer.Typer(add_completion=False, help="JD-field pipeline commands.")
_console = Console()
_err_console = Console(stderr=True)


@app.command("judge")
def judge(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report the jd_judge pairs that would be judged, without calling Gemini or writing to the database.",
    ),
) -> None:
    """Judge surviving JDs against each user's criteria and write jd_judge decisions."""
    engine = build_engine()
    plans = plan_judge_jd(engine)

    if not plans:
        typer.echo("No new jd_judge candidates. Nothing to do.")
        return

    if dry_run:
        report = render_judge_jd_plan(plans)
        if report:
            _err_console.print(report)
        fmt = TuiFormatter()
        fmt.info(f"[dry-run] {len(plans)} jd_judge pair(s) would be judged")
        _err_console.print(fmt.render())
        return

    fmt = TuiFormatter()
    fmt.info(f"Judging {len(plans)} jd_judge candidate(s)")
    _err_console.print(fmt.render())

    current_user_id: UUID | None = None
    written = 0
    for result in execute_judge_jd_plan(engine, plans):
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
    summary_fmt.success(f"{written} jd_judge decision(s) written")
    _console.print(summary_fmt.render())

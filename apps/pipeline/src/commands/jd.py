from uuid import UUID

import typer

from db import build_engine
from steps.judge_jd import (
    execute_judge_jd_plan,
    plan_judge_jd,
    render_judge_jd_plan,
)

app = typer.Typer(add_completion=False, help="JD-field pipeline commands.")


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

    report = render_judge_jd_plan(plans)
    if report:
        typer.echo(report, err=True)

    if dry_run:
        typer.echo(f"[dry-run] {len(plans)} jd_judge pair(s) would be judged")
        return

    typer.echo(f"\nJudging {len(plans)} jd_judge candidate(s)", err=True)
    current_user_id: UUID | None = None
    written = 0
    for result in execute_judge_jd_plan(engine, plans):
        p = result.plan
        if p.user_id != current_user_id:
            typer.echo(f"\n{p.user_name} ({p.user_email})", err=True)
            current_user_id = p.user_id
        suffix = "pass" if result.passes else f"reject: {result.reason}"
        typer.echo(
            f"  - {p.source_name}/{p.source_id}  {p.title} ... {suffix}",
            err=True,
        )
        written += 1

    typer.echo(f"{written} jd_judge decision(s) written")

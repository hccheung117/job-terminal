import typer
from rich.console import Console
from rich.markdown import Markdown

from db import build_engine
from steps.judge_jd import plan_judge_jd_eval, render_judge_jd_eval
from steps.judge_title import plan_judge_title_eval, render_judge_title_eval

app = typer.Typer(add_completion=False, help="Evaluate past pipeline decisions.")


@app.command("title-judge")
def eval_title_judge() -> None:
    """Show past title_judge decisions per user (criteria + jobs + decisions). Read-only."""
    engine = build_engine()
    users = plan_judge_title_eval(engine)
    markdown = render_judge_title_eval(users)
    if markdown:
        Console().print(Markdown(markdown))


@app.command("jd-judge")
def eval_jd_judge(
    job: str | None = typer.Option(
        None,
        "--job",
        metavar="SOURCE/ID",
        help="Inspection shortcut: show only this one job's decision and its full JD (format: source_name/source_id).",
    ),
) -> None:
    """Show past jd_judge decisions per user (criteria + jobs + decisions). Read-only."""
    job_key: tuple[str, str] | None = None
    if job is not None:
        if "/" not in job:
            raise typer.BadParameter("--job must be in the form source_name/source_id")
        source_name, source_id = job.split("/", 1)
        job_key = (source_name, source_id)
    engine = build_engine()
    users = plan_judge_jd_eval(engine)
    markdown = render_judge_jd_eval(users, job=job_key)
    if markdown:
        Console().print(Markdown(markdown))

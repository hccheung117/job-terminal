import typer
from rich.console import Console
from rich.markdown import Markdown

from db import build_engine
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

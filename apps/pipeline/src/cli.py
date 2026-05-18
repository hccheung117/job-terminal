import typer
from dotenv import load_dotenv

from paths import ENV_FILE

load_dotenv(ENV_FILE)

from commands.eval import app as eval_app  # noqa: E402
from commands.jd import app as jd_app  # noqa: E402
from commands.report import report as report_command  # noqa: E402
from commands.title import app as title_app  # noqa: E402

app = typer.Typer(add_completion=False, help="Post-scrape pipeline commands.")
app.add_typer(title_app, name="title")
app.add_typer(jd_app, name="jd")
app.add_typer(eval_app, name="eval")
app.command("report")(report_command)


if __name__ == "__main__":
    app()

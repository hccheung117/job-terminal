from pathlib import Path

import typer
from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(APP_ROOT / ".env")

from commands.report import report as report_command  # noqa: E402
from commands.title import app as title_app  # noqa: E402

app = typer.Typer(add_completion=False, help="Post-scrape pipeline commands.")
app.add_typer(title_app, name="title")
app.command("report")(report_command)


if __name__ == "__main__":
    app()

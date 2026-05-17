import typer
from dotenv import load_dotenv

from paths import APP_ROOT

load_dotenv(APP_ROOT / ".env")

from commands.enrich import enrich as enrich_command  # noqa: E402
from commands.scrape import scrape as scrape_command  # noqa: E402
from commands.upload import upload as upload_command  # noqa: E402

app = typer.Typer(add_completion=False, help="Scrape LinkedIn jobs by keyword group.")
app.command("scrape")(scrape_command)
app.command("enrich")(enrich_command)
app.command("upload")(upload_command)


if __name__ == "__main__":
    app()

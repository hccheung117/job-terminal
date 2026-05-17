import typer

from commands.title import app as title_app

app = typer.Typer(add_completion=False, help="Post-scrape pipeline commands.")
app.add_typer(title_app, name="title")


if __name__ == "__main__":
    app()

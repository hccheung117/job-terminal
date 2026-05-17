import os
from pathlib import Path

import jobspy_patch  # noqa: F401  # patches LinkedIn date_posted selector
import typer
from dotenv import load_dotenv
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlmodel import create_engine

from services.enrich import execute_enrich_plan, plan_enrich, render_enrich_plan
from services.jobs import (
    execute_upload_plan,
    plan_upload_snapshots,
    render_upload_plan,
    upload_counts,
)
from services.keywords import load_groups
from services.scrape import build_scrape_plan, execute_scrape_plan, render_scrape_plan

APP_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS_DIR = APP_ROOT.parents[1] / "data" / "snapshots"

load_dotenv(APP_ROOT / ".env")

SCRAPE_PARAMS: dict = {
    "site_name": ["linkedin"],
    "location": "Ireland",
    "results_wanted": 100,
    "hours_old": 24,
}

app = typer.Typer(add_completion=False, help="Scrape LinkedIn jobs by keyword group.")


def _build_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        typer.echo(
            "DATABASE_URL is not set. Set it to a Supabase Postgres URL "
            "using the postgresql+psycopg:// scheme.",
            err=True,
        )
        raise typer.Exit(code=1)
    return create_engine(database_url, poolclass=NullPool)


@app.command("scrape")
def scrape(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the groups, keywords, and output paths that would be scraped, without calling the scraper.",
    ),
) -> None:
    engine = _build_engine()

    groups = load_groups(engine)
    if not groups:
        typer.echo("No keywords found in keywords. Nothing to do.")
        raise typer.Exit(code=0)

    plans = build_scrape_plan(groups, SNAPSHOTS_DIR, SCRAPE_PARAMS)

    if dry_run:
        typer.echo(render_scrape_plan(plans, SCRAPE_PARAMS))
        return

    failures = execute_scrape_plan(plans)
    for group, message in failures:
        typer.echo(f"Group '{group}' failed: {message}", err=True)

    if failures:
        failed_groups = ", ".join(group for group, _ in failures)
        typer.echo(f"Failed groups: {failed_groups}", err=True)
        raise typer.Exit(code=1)


@app.command("enrich")
def enrich(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report how many survivors would have JDs fetched, without calling LinkedIn.",
    ),
) -> None:
    engine = _build_engine()
    plan = plan_enrich(engine)

    if dry_run:
        render_enrich_plan(plan)
        typer.echo(f"[dry-run] {len(plan.survivor_ids)} JDs would be fetched")
        return

    fetched = execute_enrich_plan(engine, plan)
    typer.echo(f"{fetched} JDs fetched")


@app.command("upload")
def upload(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report the rows that would be upserted per snapshot, without writing to the database.",
    ),
) -> None:
    engine = _build_engine()
    groups = load_groups(engine)
    plans = plan_upload_snapshots(SNAPSHOTS_DIR, groups)

    if not plans:
        typer.echo("No snapshots found in data/snapshots/. Nothing to do.")
        return

    if dry_run:
        render_upload_plan(plans)
        for group, n in upload_counts(plans).items():
            typer.echo(f"[dry-run] {group}: {n} rows would be upserted")
        return

    counts = execute_upload_plan(engine, plans)
    for group, n in counts.items():
        typer.echo(f"{group}: {n} rows upserted")


if __name__ == "__main__":
    app()

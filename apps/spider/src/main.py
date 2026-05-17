import csv
import os
import re
from pathlib import Path

import jobspy_patch  # noqa: F401  # patches LinkedIn date_posted selector
import typer
from dotenv import load_dotenv
from jobspy import scrape_jobs
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlmodel import create_engine

from services.jobs import upload_snapshots
from services.keywords import load_groups

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


def normalize_group_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "group"


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


def run_group(group: str, keywords: list[str]) -> None:
    search_term = " OR ".join(keywords)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SNAPSHOTS_DIR / f"linkedin_{normalize_group_name(group)}.csv"
    print(f"Running group '{group}' with search term: {search_term}")
    jobs = scrape_jobs(search_term=search_term, **SCRAPE_PARAMS)
    print(f"Found {len(jobs)} jobs for group '{group}'")
    jobs.to_csv(output_path, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)


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

    if dry_run:
        site_name = ", ".join(SCRAPE_PARAMS["site_name"])
        group_label = "group" if len(groups) == 1 else "groups"
        typer.echo(
            f"[dry-run] {site_name} | {SCRAPE_PARAMS['location']} | "
            f"{SCRAPE_PARAMS['results_wanted']} results/group | "
            f"last {SCRAPE_PARAMS['hours_old']}h | {len(groups)} {group_label}"
        )
        typer.echo()
        for group, keywords in groups.items():
            search_term = " OR ".join(keywords)
            keyword_label = "keyword" if len(keywords) == 1 else "keywords"
            typer.echo(f"{group} ({len(keywords)} {keyword_label})")
            typer.echo(f"  query: {search_term}")
        return

    failures: list[str] = []
    for group, keywords in groups.items():
        try:
            run_group(group, keywords)
        except Exception as exc:
            failures.append(group)
            typer.echo(f"Group '{group}' failed: {exc}", err=True)

    if failures:
        typer.echo(f"Failed groups: {', '.join(failures)}", err=True)
        raise typer.Exit(code=1)


@app.command("upload")
def upload() -> None:
    engine = _build_engine()
    counts = upload_snapshots(engine, SNAPSHOTS_DIR)
    if not counts:
        typer.echo("No snapshots found in data/snapshots/. Nothing to do.")
        return
    for group, n in counts.items():
        typer.echo(f"{group}: {n} rows upserted")


if __name__ == "__main__":
    app()

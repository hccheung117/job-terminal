from dataclasses import dataclass
from pathlib import Path

import jobspy_patch  # noqa: F401  # patches LinkedIn date_posted selector
import typer
from jobspy import scrape_jobs

from db import build_engine
from paths import SNAPSHOTS_DIR
from services.keywords import load_groups
from services.snapshots import snapshot_path, write_snapshot_csv

SCRAPE_PARAMS: dict = {
    "site_name": ["linkedin"],
    "location": "Ireland",
    "results_wanted": 100,
    "hours_old": 24,
}


@dataclass(frozen=True)
class ScrapeGroupPlan:
    group: str
    keywords: list[str]
    search_term: str
    output_path: Path
    scrape_params: dict


def _build_plan(
    groups: dict[str, list[str]],
    snapshots_dir: Path,
    scrape_params: dict,
) -> list[ScrapeGroupPlan]:
    return [
        ScrapeGroupPlan(
            group=group,
            keywords=keywords,
            search_term=" OR ".join(keywords),
            output_path=snapshot_path(snapshots_dir, group),
            scrape_params=scrape_params,
        )
        for group, keywords in groups.items()
    ]


def _render_plan(plans: list[ScrapeGroupPlan], scrape_params: dict) -> str:
    site_name = ", ".join(scrape_params["site_name"])
    group_label = "group" if len(plans) == 1 else "groups"
    lines = [
        f"[dry-run] {site_name} | {scrape_params['location']} | "
        f"{scrape_params['results_wanted']} results/group | "
        f"last {scrape_params['hours_old']}h | {len(plans)} {group_label}",
        "",
    ]
    for plan in plans:
        keyword_label = "keyword" if len(plan.keywords) == 1 else "keywords"
        lines.append(f"{plan.group} ({len(plan.keywords)} {keyword_label})")
        lines.append(f"  query: {plan.search_term}")
        lines.append(f"  output: {plan.output_path}")
    return "\n".join(lines)


def _execute_plan(plans: list[ScrapeGroupPlan]) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    for plan in plans:
        try:
            print(f"Running group '{plan.group}' with search term: {plan.search_term}")
            jobs = scrape_jobs(search_term=plan.search_term, **plan.scrape_params)
            print(f"Found {len(jobs)} jobs for group '{plan.group}'")
            write_snapshot_csv(jobs, plan.output_path)
        except Exception as exc:
            failures.append((plan.group, str(exc)))
    return failures


def scrape(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the groups, keywords, and output paths that would be scraped, without calling the scraper.",
    ),
) -> None:
    engine = build_engine()

    groups = load_groups(engine)
    if not groups:
        typer.echo("No keywords found in keywords. Nothing to do.")
        raise typer.Exit(code=0)

    plans = _build_plan(groups, SNAPSHOTS_DIR, SCRAPE_PARAMS)

    if dry_run:
        typer.echo(_render_plan(plans, SCRAPE_PARAMS))
        return

    failures = _execute_plan(plans)
    for group, message in failures:
        typer.echo(f"Group '{group}' failed: {message}", err=True)

    if failures:
        failed_groups = ", ".join(group for group, _ in failures)
        typer.echo(f"Failed groups: {failed_groups}", err=True)
        raise typer.Exit(code=1)

from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import jobspy_patch  # noqa: F401  # patches LinkedIn date_posted selector
import typer
from jobspy import scrape_jobs
from job_terminal_tui import TuiFormatter
from rich.console import Console

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

_console = Console()
_err_console = Console(stderr=True)


@dataclass(frozen=True)
class ScrapeGroupPlan:
    group: str
    keywords: list[str]
    search_term: str
    output_path: Path
    scrape_params: dict


@dataclass
class ScrapeGroupResult:
    plan: ScrapeGroupPlan
    job_count: int | None = None
    error: str | None = None


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
    fmt = TuiFormatter()
    fmt.info(
        f"[dry-run] {site_name} | {scrape_params['location']} | "
        f"{scrape_params['results_wanted']} results/group | "
        f"last {scrape_params['hours_old']}h | {len(plans)} {group_label}"
    )
    for plan in plans:
        keyword_label = "keyword" if len(plan.keywords) == 1 else "keywords"
        fmt.header(
            f"{plan.group} ({len(plan.keywords)} {keyword_label})"
        )
        fmt.info(f"query: {plan.search_term}", indent=2)
        fmt.info(f"output: {plan.output_path}", indent=2)
    return fmt.render()


def _execute_plan(
    plans: list[ScrapeGroupPlan],
    scrape_jobs_fn: Callable[..., object] = scrape_jobs,
) -> Generator[ScrapeGroupResult, None, None]:
    for plan in plans:
        try:
            jobs = scrape_jobs_fn(search_term=plan.search_term, **plan.scrape_params)
            write_snapshot_csv(jobs, plan.output_path)
            yield ScrapeGroupResult(plan=plan, job_count=len(jobs))
        except Exception as exc:
            yield ScrapeGroupResult(plan=plan, error=str(exc))


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
        _console.print(_render_plan(plans, SCRAPE_PARAMS))
        return

    failures: list[tuple[str, str]] = []
    total_jobs = 0
    for plan in plans:
        fmt = TuiFormatter()
        fmt.info(f"Scraping group '{plan.group}' ({plan.search_term})")
        _console.print(fmt.render())
        result = next(_execute_plan([plan]))
        plan = result.plan
        if result.error is not None:
            failures.append((plan.group, result.error))
            continue
        total_jobs += result.job_count or 0
        fmt = TuiFormatter()
        fmt.success(f"Found {result.job_count} jobs for group '{plan.group}'")
        _console.print(fmt.render())

    for group, message in failures:
        fmt = TuiFormatter()
        fmt.error(f"Group '{group}' failed: {message}")
        _err_console.print(fmt.render())

    if failures:
        failed_groups = ", ".join(group for group, _ in failures)
        fmt = TuiFormatter()
        fmt.error(f"Failed groups: {failed_groups}")
        _err_console.print(fmt.render())
        raise typer.Exit(code=1)

    fmt = TuiFormatter()
    fmt.success(f"Found {total_jobs} jobs across {len(plans)} group(s)")
    _console.print(fmt.render())

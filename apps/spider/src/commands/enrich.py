import sys
from dataclasses import dataclass

import typer
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text
from sqlmodel import Session

from db import build_engine
from services.linkedin import build_scraper, fetch_jd, polite_sleep
from services.jobs import update_jd

SOURCE_NAME = "linkedin"
TITLE_STEP = "title_filter"


@dataclass
class EnrichPlan:
    survivor_ids: list[str]


def _build_plan(engine: Engine) -> EnrichPlan:
    """Find jobs that need JD fetched.

    Survivor = jobs.jd IS NULL AND at least one user passed title_filter
    (score=1) for this job.
    """
    sql = text(
        "SELECT j.source_id FROM jobs j "
        "WHERE j.source_name = :source_name AND j.jd IS NULL "
        "  AND EXISTS ("
        "    SELECT 1 FROM decisions d "
        "    WHERE d.source_name = j.source_name "
        "      AND d.source_id = j.source_id "
        "      AND d.step = :step "
        "      AND d.score = 1"
        "  )"
    )
    with Session(engine) as session:
        survivor_ids = [
            row[0]
            for row in session.exec(
                sql.bindparams(source_name=SOURCE_NAME, step=TITLE_STEP)
            )
        ]
    return EnrichPlan(survivor_ids=survivor_ids)


def _render_plan(plan: EnrichPlan) -> None:
    print(f"survivors to fetch: {len(plan.survivor_ids)}", file=sys.stderr)


def _execute_plan(engine: Engine, plan: EnrichPlan) -> int:
    if not plan.survivor_ids:
        return 0

    scraper = build_scraper()
    fetched = 0
    for source_id in plan.survivor_ids:
        jd = fetch_jd(scraper, source_id)
        if jd:
            update_jd(engine, source_id, jd)
            fetched += 1
        polite_sleep(scraper)
    return fetched


def enrich(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report how many survivors would have JDs fetched, without calling LinkedIn.",
    ),
) -> None:
    engine = build_engine()
    plan = _build_plan(engine)

    if dry_run:
        _render_plan(plan)
        typer.echo(f"[dry-run] {len(plan.survivor_ids)} JDs would be fetched")
        return

    fetched = _execute_plan(engine, plan)
    typer.echo(f"{fetched} JDs fetched")

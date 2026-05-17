import random
import sys
import time
from dataclasses import dataclass

from jobspy.linkedin import LinkedIn
from jobspy.model import DescriptionFormat, ScraperInput, Site
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text
from sqlmodel import Session

SOURCE_NAME = "linkedin"
TITLE_STEP = "title_filter"
LINKEDIN_ID_PREFIX = "li-"


@dataclass
class EnrichPlan:
    survivor_ids: list[str]
    skipped_rejected_count: int


def plan_enrich(engine: Engine) -> EnrichPlan:
    """Find jobs that need JD fetched.

    Survivor = jobs.jd IS NULL AND not commonly-rejected at title_filter step.
    Commonly-rejected = every user has a rejection (score <= 0) decision at title_filter
    for this job. A user with no decision yet keeps the job alive.
    """
    sql = text(
        "WITH rejected AS ("
        "  SELECT d.source_id FROM decisions d "
        "  WHERE d.source_name = :source_name "
        "    AND d.step = :step "
        "    AND d.score <= 0 "
        "  GROUP BY d.source_id "
        "  HAVING COUNT(DISTINCT d.user_id) = (SELECT COUNT(*) FROM users)"
        ") "
        "SELECT j.source_id, j.source_id IN (SELECT source_id FROM rejected) AS rejected "
        "FROM jobs j "
        "WHERE j.source_name = :source_name AND j.jd IS NULL"
    )
    survivor_ids: list[str] = []
    skipped = 0
    with Session(engine) as session:
        for source_id, rejected in session.exec(
            sql.bindparams(source_name=SOURCE_NAME, step=TITLE_STEP)
        ):
            if rejected:
                skipped += 1
            else:
                survivor_ids.append(source_id)
    return EnrichPlan(survivor_ids=survivor_ids, skipped_rejected_count=skipped)


def render_enrich_plan(plan: EnrichPlan) -> None:
    print(
        f"survivors to fetch: {len(plan.survivor_ids)} | "
        f"skipped (commonly rejected at {TITLE_STEP}): {plan.skipped_rejected_count}",
        file=sys.stderr,
    )


def execute_enrich_plan(engine: Engine, plan: EnrichPlan) -> int:
    if not plan.survivor_ids:
        return 0

    scraper = LinkedIn()
    scraper.scraper_input = ScraperInput(
        site_type=[Site.LINKEDIN],
        description_format=DescriptionFormat.MARKDOWN,
    )

    update_sql = text(
        "UPDATE jobs SET jd = :jd "
        "WHERE source_name = :source_name AND source_id = :source_id"
    )

    fetched = 0
    with Session(engine) as session:
        for source_id in plan.survivor_ids:
            job_id = source_id.removeprefix(LINKEDIN_ID_PREFIX)
            details = scraper._get_job_details(job_id)
            description = details.get("description")
            if not description:
                time.sleep(scraper.delay + random.uniform(0, scraper.band_delay))
                continue
            session.exec(update_sql.bindparams(
                jd=description,
                source_name=SOURCE_NAME,
                source_id=source_id,
            ))
            session.commit()
            fetched += 1
            time.sleep(scraper.delay + random.uniform(0, scraper.band_delay))
    return fetched

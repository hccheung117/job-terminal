import csv
from dataclasses import dataclass
from pathlib import Path

from jobspy import scrape_jobs

SNAPSHOT_PREFIX = "linkedin_"


@dataclass(frozen=True)
class ScrapeGroupPlan:
    group: str
    keywords: list[str]
    search_term: str
    output_path: Path
    scrape_params: dict


def build_scrape_plan(
    groups: dict[str, list[str]],
    snapshots_dir: Path,
    scrape_params: dict,
) -> list[ScrapeGroupPlan]:
    return [
        ScrapeGroupPlan(
            group=group,
            keywords=keywords,
            search_term=" OR ".join(keywords),
            output_path=snapshots_dir / f"{SNAPSHOT_PREFIX}{group}.csv",
            scrape_params=scrape_params,
        )
        for group, keywords in groups.items()
    ]


def render_scrape_plan(plans: list[ScrapeGroupPlan], scrape_params: dict) -> str:
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


def execute_scrape_plan(plans: list[ScrapeGroupPlan]) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    if not plans:
        return failures

    plans[0].output_path.parent.mkdir(parents=True, exist_ok=True)
    for plan in plans:
        try:
            print(f"Running group '{plan.group}' with search term: {plan.search_term}")
            jobs = scrape_jobs(search_term=plan.search_term, **plan.scrape_params)
            print(f"Found {len(jobs)} jobs for group '{plan.group}'")
            jobs.to_csv(
                plan.output_path,
                quoting=csv.QUOTE_NONNUMERIC,
                escapechar="\\",
                index=False,
            )
        except Exception as exc:
            failures.append((plan.group, str(exc)))
    return failures

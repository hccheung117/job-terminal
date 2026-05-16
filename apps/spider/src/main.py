import csv
import os
import re
import sys
from pathlib import Path

import jobspy_patch  # noqa: F401  # patches LinkedIn date_posted selector
from dotenv import load_dotenv
from jobspy import scrape_jobs

from service import load_groups

APP_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS_DIR = APP_ROOT.parents[1] / "data" / "snapshots"

load_dotenv(APP_ROOT / ".env")


def normalize_group_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "group"


def run_group(group: str, keywords: list[str]) -> None:
    search_term = " OR ".join(keywords)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SNAPSHOTS_DIR / f"linkedin_{normalize_group_name(group)}.csv"
    print(f"Running group '{group}' with search term: {search_term}")
    jobs = scrape_jobs(
        site_name=["linkedin"],
        search_term=search_term,
        location="Ireland",
        results_wanted=25,
        hours_old=24,
    )
    print(f"Found {len(jobs)} jobs for group '{group}'")
    jobs.to_csv(output_path, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            "DATABASE_URL is not set. "
            "Set it to a Supabase Postgres URL using the "
            "postgresql+psycopg:// scheme.",
            file=sys.stderr,
        )
        return 1

    groups = load_groups(database_url)

    if not groups:
        print("No keywords found in spider_keywords. Nothing to do.")
        return 0

    failures: list[str] = []
    for group, keywords in groups.items():
        try:
            run_group(group, keywords)
        except Exception as exc:
            failures.append(group)
            print(f"Group '{group}' failed: {exc}", file=sys.stderr)

    if failures:
        print(f"Failed groups: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

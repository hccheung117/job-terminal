import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text
from sqlmodel import Session

from job_terminal_models import Job
from services.title_filter import split_by_title, title_pattern

SOURCE_NAME = "linkedin"
SNAPSHOT_PREFIX = "linkedin_"


@dataclass
class UploadSnapshotPlan:
    group: str
    csv_path: Path
    records: list[dict]
    kept_titles: list[str]
    dropped_titles: list[str]
    keywords: list[str] | None = None
    warning: str | None = None


def _group_from_filename(path: Path) -> str:
    return path.stem[len(SNAPSHOT_PREFIX):]


def _parse_published_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _row_to_job(row: dict[str, str], group: str) -> dict | None:
    source_id = (row.get("id") or "").strip()
    if not source_id:
        return None
    return {
        "source_name": SOURCE_NAME,
        "source_id": source_id,
        "groups": [group],
        "location": row.get("location") or None,
        "title": row.get("title") or None,
        "jd": row.get("description") or None,
        "url": row.get("job_url") or row.get("url") or None,
        "published_at": _parse_published_at(row.get("date_posted")),
    }


def plan_upload_snapshots(
    snapshots_dir: Path,
    groups: dict[str, list[str]],
) -> list[UploadSnapshotPlan]:
    plans: list[UploadSnapshotPlan] = []
    if not snapshots_dir.exists():
        return plans

    for csv_path in sorted(snapshots_dir.glob(f"{SNAPSHOT_PREFIX}*.csv")):
        if csv_path.stat().st_size == 0:
            continue
        group = _group_from_filename(csv_path)
        keywords = groups.get(group)
        if not keywords:
            plans.append(
                UploadSnapshotPlan(
                    group=group,
                    csv_path=csv_path,
                    records=[],
                    kept_titles=[],
                    dropped_titles=[],
                    warning=(
                        f"no keywords for group '{group}'; skipping {csv_path.name}"
                    ),
                ),
            )
            continue

        pattern = title_pattern(keywords)
        if pattern is None:
            plans.append(
                UploadSnapshotPlan(
                    group=group,
                    csv_path=csv_path,
                    records=[],
                    kept_titles=[],
                    dropped_titles=[],
                    keywords=keywords,
                ),
            )
            continue

        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        df, kept_titles, dropped_titles = split_by_title(df, pattern)

        records = [_row_to_job(row, group) for row in df.to_dict("records")]
        records = [r for r in records if r is not None]

        plans.append(
            UploadSnapshotPlan(
                group=group,
                csv_path=csv_path,
                records=records,
                kept_titles=kept_titles,
                dropped_titles=dropped_titles,
                keywords=keywords,
            ),
        )

    return plans


def render_upload_plan(plans: list[UploadSnapshotPlan]) -> None:
    for plan in plans:
        if plan.warning:
            print(f"warning: {plan.warning}", file=sys.stderr)
            continue
        if plan.keywords is None:
            continue
        print(f"\n{plan.csv_path.name}  (group: {plan.group})", file=sys.stderr)
        print(f"  keywords: {', '.join(plan.keywords)}", file=sys.stderr)
        print(
            f"  kept {len(plan.kept_titles)} / dropped {len(plan.dropped_titles)} / "
            f"total {len(plan.kept_titles) + len(plan.dropped_titles)}",
            file=sys.stderr,
        )
        for title in plan.kept_titles:
            print(f"  + {title}", file=sys.stderr)
        for title in plan.dropped_titles:
            print(f"  - {title}", file=sys.stderr)


def execute_upload_plan(
    engine: Engine,
    plans: list[UploadSnapshotPlan],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    merge_groups = text(
        "COALESCE("
        "(SELECT ARRAY_AGG(DISTINCT g) "
        "FROM UNNEST(jobs.groups || EXCLUDED.groups) AS merged(g) "
        "WHERE g <> ''), '{}')"
    )

    for plan in plans:
        if plan.warning:
            print(f"warning: {plan.warning}", file=sys.stderr)
            counts[plan.group] = 0
            continue

        if not plan.records:
            counts[plan.group] = 0
            continue

        stmt = insert(Job).values(plan.records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_name", "source_id"],
            set_={
                "groups": merge_groups,
                "location": stmt.excluded.location,
                "title": stmt.excluded.title,
                "jd": stmt.excluded.jd,
                "url": stmt.excluded.url,
                "published_at": stmt.excluded.published_at,
            },
        )

        with Session(engine) as session:
            session.exec(stmt)
            session.commit()

        counts[plan.group] = len(plan.records)

    return counts


def upload_counts(plans: list[UploadSnapshotPlan]) -> dict[str, int]:
    return {plan.group: len(plan.records) for plan in plans}

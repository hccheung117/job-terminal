import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text
from sqlmodel import Session

from job_terminal_models import Job

SOURCE_NAME = "linkedin"
SNAPSHOT_PREFIX = "linkedin_"


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


def _title_pattern(keywords: list[str]) -> str | None:
    parts = [re.escape(k.strip()) for k in keywords if k and k.strip()]
    if not parts:
        return None
    return r"\b(?:" + "|".join(parts) + r")\b"


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


def upload_snapshots(
    engine: Engine,
    snapshots_dir: Path,
    groups: dict[str, list[str]],
    dry_run: bool = False,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not snapshots_dir.exists():
        return counts

    merge_groups = text(
        "COALESCE("
        "(SELECT ARRAY_AGG(DISTINCT g) "
        "FROM UNNEST(jobs.groups || EXCLUDED.groups) AS merged(g) "
        "WHERE g <> ''), '{}')"
    )

    for csv_path in sorted(snapshots_dir.glob(f"{SNAPSHOT_PREFIX}*.csv")):
        if csv_path.stat().st_size == 0:
            continue
        group = _group_from_filename(csv_path)
        keywords = groups.get(group)
        if not keywords:
            print(
                f"warning: no keywords for group '{group}'; skipping {csv_path.name}",
                file=sys.stderr,
            )
            counts[group] = 0
            continue

        pattern = _title_pattern(keywords)
        if pattern is None:
            counts[group] = 0
            continue

        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        matched = df["title"].str.contains(pattern, case=False, regex=True, na=False)

        if dry_run:
            kept_titles = df.loc[matched, "title"].tolist()
            dropped_titles = df.loc[~matched, "title"].tolist()
            print(f"\n{csv_path.name}  (group: {group})", file=sys.stderr)
            print(f"  keywords: {', '.join(keywords)}", file=sys.stderr)
            print(
                f"  kept {len(kept_titles)} / dropped {len(dropped_titles)} / total {len(df)}",
                file=sys.stderr,
            )
            for t in kept_titles:
                print(f"  + {t}", file=sys.stderr)
            for t in dropped_titles:
                print(f"  - {t}", file=sys.stderr)

        df = df[matched]

        records = [_row_to_job(row, group) for row in df.to_dict("records")]
        records = [r for r in records if r is not None]

        if not records:
            counts[group] = 0
            continue

        if not dry_run:
            stmt = insert(Job).values(records)
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

        counts[group] = len(records)

    return counts

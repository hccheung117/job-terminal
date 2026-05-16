import csv
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text
from sqlmodel import Session

from job_terminal_models import Job

SOURCE_NAME = "linkedin"
SNAPSHOT_PREFIX = "linkedin_"


def _group_from_filename(path: Path) -> str:
    return path.stem[len(SNAPSHOT_PREFIX):]


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
        "published_at": row.get("date_posted") or None,
    }


def upload_snapshots(engine: Engine, snapshots_dir: Path) -> dict[str, int]:
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
        records: list[dict] = []
        with csv_path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                record = _row_to_job(row, group)
                if record is not None:
                    records.append(record)

        if not records:
            counts[group] = 0
            continue

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

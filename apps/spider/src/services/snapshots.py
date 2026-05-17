import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from services.title_filter import split_by_title, title_pattern

SOURCE_NAME = "linkedin"
SNAPSHOT_PREFIX = "linkedin_"


def snapshot_path(snapshots_dir: Path, group: str) -> Path:
    return snapshots_dir / f"{SNAPSHOT_PREFIX}{group}.csv"


def iter_snapshots(snapshots_dir: Path) -> list[Path]:
    if not snapshots_dir.exists():
        return []
    return [
        p for p in sorted(snapshots_dir.glob(f"{SNAPSHOT_PREFIX}*.csv"))
        if p.stat().st_size > 0
    ]


def group_from_filename(path: Path) -> str:
    return path.stem[len(SNAPSHOT_PREFIX):]


def write_snapshot_csv(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)


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


def load_snapshot_records(
    csv_path: Path,
    group: str,
    keywords: list[str],
) -> tuple[list[dict], list[str], list[str]]:
    """Read a snapshot CSV and split by title pattern.

    Returns (records, kept_titles, dropped_titles).
    If the keyword list yields no usable pattern, returns ([], [], []).
    """
    pattern = title_pattern(keywords)
    if pattern is None:
        return [], [], []

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df, kept_titles, dropped_titles = split_by_title(df, pattern)

    records = [_row_to_job(row, group) for row in df.to_dict("records")]
    records = [r for r in records if r is not None]
    return records, kept_titles, dropped_titles

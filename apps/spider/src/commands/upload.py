from dataclasses import dataclass
from pathlib import Path

import typer
from sqlalchemy.engine import Engine

from db import build_engine
from paths import SNAPSHOTS_DIR
from services.jobs import upsert_jobs
from services.keywords import load_groups
from services.snapshots import (
    group_from_filename,
    iter_snapshots,
    load_snapshot_records,
)


@dataclass
class UploadSnapshotPlan:
    group: str
    csv_path: Path
    records: list[dict]
    kept_titles: list[str]
    dropped_titles: list[str]
    keywords: list[str] | None = None
    warning: str | None = None


def _build_plan(
    snapshots_dir: Path,
    groups: dict[str, list[str]],
) -> list[UploadSnapshotPlan]:
    plans: list[UploadSnapshotPlan] = []
    for csv_path in iter_snapshots(snapshots_dir):
        group = group_from_filename(csv_path)
        keywords = groups.get(group)
        if not keywords:
            plans.append(
                UploadSnapshotPlan(
                    group=group,
                    csv_path=csv_path,
                    records=[],
                    kept_titles=[],
                    dropped_titles=[],
                    warning=f"no keywords for group '{group}'; skipping {csv_path.name}",
                )
            )
            continue

        records, kept_titles, dropped_titles = load_snapshot_records(
            csv_path, group, keywords
        )
        plans.append(
            UploadSnapshotPlan(
                group=group,
                csv_path=csv_path,
                records=records,
                kept_titles=kept_titles,
                dropped_titles=dropped_titles,
                keywords=keywords,
            )
        )
    return plans


def _render_plan(plans: list[UploadSnapshotPlan]) -> str:
    lines: list[str] = []
    for plan in plans:
        if plan.warning:
            lines.append(f"warning: {plan.warning}")
            continue
        if plan.keywords is None:
            continue
        lines.append(f"\n{plan.csv_path.name}  (group: {plan.group})")
        lines.append(f"  keywords: {', '.join(plan.keywords)}")
        lines.append(
            f"  kept {len(plan.kept_titles)} / dropped {len(plan.dropped_titles)} / "
            f"total {len(plan.kept_titles) + len(plan.dropped_titles)}"
        )
        for title in plan.kept_titles:
            lines.append(f"  + {title}")
        for title in plan.dropped_titles:
            lines.append(f"  - {title}")
    return "\n".join(lines)


def _execute_plan(
    engine: Engine,
    plans: list[UploadSnapshotPlan],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for plan in plans:
        if plan.warning:
            counts[plan.group] = 0
            continue
        counts[plan.group] = upsert_jobs(engine, plan.records)
    return counts


def _plan_counts(plans: list[UploadSnapshotPlan]) -> dict[str, int]:
    return {plan.group: len(plan.records) for plan in plans}


def upload(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report the rows that would be upserted per snapshot, without writing to the database.",
    ),
) -> None:
    engine = build_engine()
    groups = load_groups(engine)
    plans = _build_plan(SNAPSHOTS_DIR, groups)

    if not plans:
        typer.echo("No snapshots found in data/snapshots/. Nothing to do.")
        return

    if dry_run:
        typer.echo(_render_plan(plans), err=True)
        for group, n in _plan_counts(plans).items():
            typer.echo(f"[dry-run] {group}: {n} rows would be upserted")
        return

    typer.echo(_render_plan(plans), err=True)
    counts = _execute_plan(engine, plans)
    for group, n in counts.items():
        typer.echo(f"{group}: {n} rows upserted")

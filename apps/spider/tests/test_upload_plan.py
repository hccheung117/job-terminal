from pathlib import Path

from commands.upload import _build_plan, _plan_counts, _render_plan

SNAPSHOT_HEADER = "id,title,location,description,job_url,date_posted\n"


def _write_snapshot(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = [SNAPSHOT_HEADER]
    for source_id, title in rows:
        lines.append(f"{source_id},{title},,,,\n")
    path.write_text("".join(lines), encoding="utf-8")


def test_plan_upload_snapshots_filters_titles(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    _write_snapshot(
        snapshots_dir / "linkedin_backend.csv",
        [
            ("1", "Senior Python Engineer"),
            ("2", "Java Developer"),
            ("3", "Python Backend Developer"),
        ],
    )
    groups = {"backend": ["python"]}

    plans = _build_plan(snapshots_dir, groups)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.group == "backend"
    assert len(plan.records) == 2
    assert plan.kept_titles == [
        "Senior Python Engineer",
        "Python Backend Developer",
    ]
    assert plan.dropped_titles == ["Java Developer"]
    assert plan.records[0]["source_id"] == "1"
    assert plan.records[0]["groups"] == ["backend"]


def test_plan_upload_snapshots_skips_unknown_group_with_warning(
    tmp_path: Path,
    capsys,
) -> None:
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    _write_snapshot(
        snapshots_dir / "linkedin_unknown.csv",
        [("1", "Some Job")],
    )
    groups: dict[str, list[str]] = {}

    plans = _build_plan(snapshots_dir, groups)

    assert len(plans) == 1
    assert plans[0].warning is not None
    assert plans[0].records == []
    assert _plan_counts(plans) == {"unknown": 0}


def test_plan_upload_snapshots_skips_empty_and_missing_dir(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    (snapshots_dir / "linkedin_empty.csv").write_text("", encoding="utf-8")
    groups = {"empty": ["python"]}

    plans = _build_plan(snapshots_dir, groups)
    assert plans == []

    missing_dir = tmp_path / "missing"
    assert _build_plan(missing_dir, groups) == []


def test_render_upload_plan_returns_details(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    _write_snapshot(
        snapshots_dir / "linkedin_backend.csv",
        [("1", "Python Engineer")],
    )
    plans = _build_plan(snapshots_dir, {"backend": ["python"]})

    report = _render_plan(plans)

    assert "linkedin_backend.csv" in report
    assert "+ Python Engineer" in report
    assert _plan_counts(plans) == {"backend": 1}

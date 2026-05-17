from pathlib import Path

from services.jobs import plan_upload_snapshots, render_upload_plan, upload_counts

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

    plans = plan_upload_snapshots(snapshots_dir, groups)

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

    plans = plan_upload_snapshots(snapshots_dir, groups)

    assert len(plans) == 1
    assert plans[0].warning is not None
    assert plans[0].records == []
    assert upload_counts(plans) == {"unknown": 0}


def test_plan_upload_snapshots_skips_empty_and_missing_dir(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    (snapshots_dir / "linkedin_empty.csv").write_text("", encoding="utf-8")
    groups = {"empty": ["python"]}

    plans = plan_upload_snapshots(snapshots_dir, groups)
    assert plans == []

    missing_dir = tmp_path / "missing"
    assert plan_upload_snapshots(missing_dir, groups) == []


def test_render_upload_plan_writes_details_to_stderr(tmp_path: Path, capsys) -> None:
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()
    _write_snapshot(
        snapshots_dir / "linkedin_backend.csv",
        [("1", "Python Engineer")],
    )
    plans = plan_upload_snapshots(snapshots_dir, {"backend": ["python"]})

    render_upload_plan(plans)

    captured = capsys.readouterr()
    assert "linkedin_backend.csv" in captured.err
    assert "+ Python Engineer" in captured.err
    assert upload_counts(plans) == {"backend": 1}

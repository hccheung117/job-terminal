from pathlib import Path

from commands.scrape import _build_plan, _render_plan

SCRAPE_PARAMS = {
    "site_name": ["linkedin"],
    "location": "Ireland",
    "results_wanted": 100,
    "hours_old": 24,
}


def test_build_scrape_plan_one_plan_per_group(tmp_path: Path) -> None:
    groups = {
        "backend": ["python", "django"],
        "data": ["sql"],
    }

    plans = _build_plan(groups, tmp_path, SCRAPE_PARAMS)

    assert len(plans) == 2
    backend = plans[0]
    assert backend.group == "backend"
    assert backend.keywords == ["python", "django"]
    assert backend.search_term == "python OR django"
    assert backend.output_path == tmp_path / "linkedin_backend.csv"
    assert backend.scrape_params == SCRAPE_PARAMS

    data = plans[1]
    assert data.group == "data"
    assert data.search_term == "sql"
    assert data.output_path == tmp_path / "linkedin_data.csv"


def test_render_scrape_plan_includes_summary_and_paths(tmp_path: Path) -> None:
    groups = {"backend": ["python"]}
    plans = _build_plan(groups, tmp_path, SCRAPE_PARAMS)

    report = _render_plan(plans, SCRAPE_PARAMS)

    assert "[dry-run] linkedin | Ireland | 100 results/group | last 24h | 1 group" in report
    assert "backend (1 keyword)" in report
    assert "query: python" in report
    assert f"output: {tmp_path / 'linkedin_backend.csv'}" in report

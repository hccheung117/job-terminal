from pathlib import Path

import pandas as pd

from commands.scrape import _build_plan, _execute_plan

SCRAPE_PARAMS = {
    "site_name": ["linkedin"],
    "location": "Ireland",
    "results_wanted": 100,
    "hours_old": 24,
}


def test_execute_scrape_plan_yields_success_and_failure(tmp_path: Path) -> None:
    groups = {"ok": ["python"], "bad": ["java"]}
    plans = _build_plan(groups, tmp_path, SCRAPE_PARAMS)

    def fake_scrape_jobs(search_term: str, **kwargs: object) -> pd.DataFrame:
        if search_term == "java":
            raise RuntimeError("scrape failed")
        return pd.DataFrame([{"id": "1", "title": "Job"}])

    results = list(_execute_plan(plans, scrape_jobs_fn=fake_scrape_jobs))

    assert len(results) == 2
    by_group = {r.plan.group: r for r in results}
    assert by_group["ok"].job_count == 1
    assert by_group["ok"].error is None
    assert by_group["bad"].error == "scrape failed"
    assert (tmp_path / "linkedin_ok.csv").exists()

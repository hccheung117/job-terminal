from datetime import datetime, timezone

from sqlmodel import Session

from conftest import add_decision, add_report_send, make_job, make_user
from steps.report import plan_report, render_report_preview


def test_report_uses_furthest_passed_step(engine):
    with Session(engine) as session:
        user = make_user(session)
        judged_pass = make_job(session, "1", "Senior Python Engineer")
        judged_reject = make_job(session, "2", "Staff Engineer")
        only_filtered = make_job(session, "3", "Backend Engineer")
        filter_rejected = make_job(session, "4", "Frontend Designer")
        add_decision(session, user.id, judged_pass, "title_filter", score=1)
        add_decision(session, user.id, judged_pass, "title_judge", score=1)
        add_decision(session, user.id, judged_reject, "title_filter", score=1)
        add_decision(session, user.id, judged_reject, "title_judge", score=0, reason="not a fit")
        add_decision(session, user.id, only_filtered, "title_filter", score=1)
        add_decision(session, user.id, filter_rejected, "title_filter", score=0, reason="stopword")

    reports = plan_report(engine)
    assert len(reports) == 1
    titles = {j.title for j in reports[0].jobs}
    assert titles == {"Senior Python Engineer"}


def test_report_uses_only_filter_when_no_judge_decisions_exist(engine):
    with Session(engine) as session:
        user = make_user(session)
        passed = make_job(session, "1", "Senior Python Engineer")
        rejected = make_job(session, "2", "Frontend Designer")
        add_decision(session, user.id, passed, "title_filter", score=1)
        add_decision(session, user.id, rejected, "title_filter", score=0, reason="stopword")

    reports = plan_report(engine)
    titles = {j.title for j in reports[0].jobs}
    assert titles == {"Senior Python Engineer"}


def test_report_ignores_earlier_steps_when_judge_exists_for_anyone(engine):
    with Session(engine) as session:
        judged_user = make_user(session, name="Alice")
        filter_only_user = make_user(session, name="Bob")
        job = make_job(session, "1", "Senior Python Engineer")
        add_decision(session, judged_user.id, job, "title_filter", score=1)
        add_decision(session, judged_user.id, job, "title_judge", score=1)
        add_decision(session, filter_only_user.id, job, "title_filter", score=1)

    reports = {r.user_name: r for r in plan_report(engine)}
    assert {j.title for j in reports["Alice"].jobs} == {"Senior Python Engineer"}
    assert reports["Bob"].jobs == []


def test_report_empty_when_user_has_no_decisions(engine):
    with Session(engine) as session:
        make_user(session)
        make_job(session, "1", "Senior Python Engineer")

    reports = plan_report(engine)
    assert reports[0].jobs == []


def test_render_report_preview_returns_markdown(engine):
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer")
        add_decision(session, user.id, job, "title_filter", score=1)

    reports = plan_report(engine)
    markdown = render_report_preview(reports)

    assert "Jobs for Alice" in markdown
    assert "Senior Python Engineer" in markdown


def test_report_includes_only_decisions_after_user_cutoff(engine):
    cutoff = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    before = datetime(2026, 5, 17, 11, 0, tzinfo=timezone.utc)
    after = datetime(2026, 5, 17, 13, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        user = make_user(session)
        old_job = make_job(session, "1", "Old Job")
        new_job = make_job(session, "2", "New Job")
        add_decision(session, user.id, old_job, "title_filter", score=1, judged_at=before)
        add_decision(session, user.id, new_job, "title_filter", score=1, judged_at=after)
        add_report_send(session, user.id, cutoff_at=cutoff)

    reports = plan_report(engine)
    assert {j.title for j in reports[0].jobs} == {"New Job"}
    assert reports[0].cutoff_at == after


def test_report_excludes_decisions_at_exact_cutoff(engine):
    cutoff = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Boundary Job")
        add_decision(session, user.id, job, "title_filter", score=1, judged_at=cutoff)
        add_report_send(session, user.id, cutoff_at=cutoff)

    reports = plan_report(engine)
    assert reports[0].jobs == []
    assert reports[0].cutoff_at is None


def test_report_uses_max_judged_at_not_published_or_first_seen(engine):
    earlier = datetime(2026, 5, 17, 9, 0, tzinfo=timezone.utc)
    later = datetime(2026, 5, 17, 15, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        user = make_user(session)
        job_a = make_job(session, "1", "A")
        job_b = make_job(session, "2", "B")
        add_decision(session, user.id, job_a, "title_filter", score=1, judged_at=earlier)
        add_decision(session, user.id, job_b, "title_filter", score=1, judged_at=later)

    reports = plan_report(engine)
    assert reports[0].cutoff_at == later


def test_report_no_cutoff_when_user_has_no_eligible_jobs(engine):
    with Session(engine) as session:
        make_user(session)
    reports = plan_report(engine)
    assert reports[0].jobs == []
    assert reports[0].cutoff_at is None


def test_report_uses_latest_cutoff_when_user_has_multiple_sends(engine):
    older = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 5, 17, 14, 0, tzinfo=timezone.utc)
    between = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    after_newer = datetime(2026, 5, 17, 15, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        user = make_user(session)
        between_job = make_job(session, "1", "Between")
        after_job = make_job(session, "2", "After")
        add_decision(session, user.id, between_job, "title_filter", score=1, judged_at=between)
        add_decision(session, user.id, after_job, "title_filter", score=1, judged_at=after_newer)
        add_report_send(session, user.id, cutoff_at=older)
        add_report_send(session, user.id, cutoff_at=newer)

    reports = plan_report(engine)
    assert {j.title for j in reports[0].jobs} == {"After"}

from sqlmodel import Session

from conftest import add_decision, make_job, make_user
from steps.report import plan_report


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

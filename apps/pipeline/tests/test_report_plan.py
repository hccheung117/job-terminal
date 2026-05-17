from sqlmodel import Session

from conftest import add_decision, make_job, make_user
from steps.report import plan_report


def test_report_excludes_only_reject_rows(engine):
    with Session(engine) as session:
        user = make_user(session)
        passed = make_job(session, "1", "Senior Python Engineer")
        rejected = make_job(session, "2", "Frontend Designer")
        untouched = make_job(session, "3", "Backend Engineer")
        add_decision(session, user.id, passed, "title_filter", score=1)
        add_decision(session, user.id, passed, "title_judge", score=1)
        add_decision(session, user.id, rejected, "title_filter", score=0, reason="stopword")

    reports = plan_report(engine)
    assert len(reports) == 1
    titles = {j.title for j in reports[0].jobs}
    assert titles == {"Senior Python Engineer", "Backend Engineer"}


def test_report_excludes_any_reject_even_with_pass(engine):
    with Session(engine) as session:
        user = make_user(session)
        job = make_job(session, "1", "Senior Python Engineer")
        add_decision(session, user.id, job, "title_filter", score=1)
        add_decision(session, user.id, job, "title_judge", score=0, reason="not a fit")

    reports = plan_report(engine)
    assert reports[0].jobs == []
